"""Patient signup site for an Ontario family doctor matching service."""

import asyncio
import csv
import io
import logging
import re
import secrets
from collections import Counter
from datetime import datetime, timezone

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import emailer, questions as q
from .config import settings
from .db import init_db, transaction
from .retention import delete_person, deidentify
from .retention import run as run_retention
from .security import RateLimiter, hash_token, new_id, new_token, now_iso

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

async def retention_loop():
    """Run the retention schedule once a day inside the web process (single-server setup)."""
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.to_thread(run_retention)
        except Exception:
            logging.getLogger("retention").exception("Retention run failed")
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(_app):
    init_db()
    task = asyncio.create_task(retention_loop()) if settings.run_retention_in_app else None
    yield
    if task:
        task.cancel()


app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(settings=settings, q=q)

rate_limiter = RateLimiter(settings.rate_limit_per_10min)
basic_auth = HTTPBasic(auto_error=False)

# Ontario postal codes start with K, L, M, N or P. D, F, I, O, Q and U are never used.
POSTAL_RE = re.compile(r"^[KLMNP][0-9][ABCEGHJ-NPRSTV-Z] ?[0-9][ABCEGHJ-NPRSTV-Z][0-9]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_DIGITS_RE = re.compile(r"\D")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Links in our emails carry private tokens; never leak them to other sites.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if settings.base_url.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def client_ip(request: Request) -> str:
    # Used only for rate limiting, never stored.
    return (
        request.headers.get("fly-client-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def render(request: Request, template: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, template, context, status_code=status_code)


# ---------------------------------------------------------------- public pages


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "index.html", values={}, errors={})


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return render(request, "privacy.html")


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


def normalize_postal(value: str) -> str:
    compact = re.sub(r"\s+", "", value or "").upper()
    if len(compact) == 6:
        return f"{compact[:3]} {compact[3:]}"
    return compact


def validate(form: dict) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    clean: dict = {}

    email = (form.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        errors["email"] = "Enter a valid email address."
    clean["email"] = email

    phone = (form.get("phone") or "").strip()
    if phone:
        digits = PHONE_DIGITS_RE.sub("", phone)
        if digits.startswith("1") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) != 10:
            errors["phone"] = "Enter a 10-digit phone number, or leave it blank."
        else:
            phone = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    clean["phone"] = phone or None

    postal = normalize_postal(form.get("postal_code", ""))
    if not POSTAL_RE.match(postal):
        errors["postal_code"] = "Enter an Ontario postal code, for example M5V 3L9."
    clean["postal_code"] = postal

    def choice(field: str, options, required: bool = True, message: str = "Choose an option."):
        value = form.get(field) or ""
        if value in q.option_keys(options) and value != "":
            clean[field] = value
        elif required:
            errors[field] = message
            clean[field] = None
        else:
            clean[field] = None

    choice("radius_km", q.RADIUS_OPTIONS, message="Choose how far you can travel.")
    choice("for_whom", q.FOR_WHOM_OPTIONS, message="Tell us who you are looking for.")
    choice("age_band", q.AGE_BAND_OPTIONS, message="Choose the age of the person who needs a doctor.")
    choice("language", q.LANGUAGE_OPTIONS, required=False)
    choice("time_without_doctor", q.TIME_WITHOUT_DOCTOR_OPTIONS, message="Choose how long it has been.")
    choice("ohip_status", q.OHIP_OPTIONS, message="Tell us about your health card.")
    choice("hcc_registered", q.HCC_OPTIONS, message="Choose an option.")
    choice("referral_source", q.REFERRAL_OPTIONS, required=False)

    household = (form.get("household_size") or "").strip()
    if household:
        if household.isdigit() and 1 <= int(household) <= 12:
            clean["household_size"] = int(household)
        else:
            errors["household_size"] = "Enter a number from 1 to 12, or leave it blank."
            clean["household_size"] = None
    else:
        clean["household_size"] = None

    clean["service_consent"] = form.get("service_consent") == "yes"
    if not clean["service_consent"]:
        errors["service_consent"] = "We need your consent to use your details for this service."

    clean["health_consent"] = form.get("health_consent") == "yes"
    clean["feedback_consent"] = form.get("feedback_consent") == "yes"
    flags = [f for f in form.get("need_flags", []) if f in q.NEED_FLAG_KEYS]
    if flags and not clean["health_consent"]:
        errors["health_consent"] = "Tick this box to let us use the health and access answers you chose, or untick those answers."
    clean["need_flags"] = sorted(set(flags)) if clean["health_consent"] else []

    return clean, errors


@app.post("/signup")
async def signup(request: Request, background: BackgroundTasks):
    form_data = await request.form()
    form = {key: form_data.get(key) for key in form_data.keys()}
    form["need_flags"] = form_data.getlist("need_flags")

    # Honeypot: real people never see or fill this field.
    if form.get("website"):
        return RedirectResponse("/thanks", status_code=303)

    if not rate_limiter.allow(client_ip(request)):
        return render(request, "index.html", status_code=429, values=form,
                      errors={"form": "Too many attempts from your connection. Please try again in a few minutes."})

    clean, errors = validate(form)
    if errors:
        return render(request, "index.html", status_code=422, values=form, errors=errors)

    created = now_iso()
    with transaction() as conn:
        existing = conn.execute("SELECT id, verified_at FROM contacts WHERE email = ?", (clean["email"],)).fetchone()
        if existing:
            # Same response either way, so the form cannot be used to check who is signed up.
            manage_token = new_token()
            if existing["verified_at"]:
                conn.execute("UPDATE contacts SET manage_token_hash = ? WHERE id = ?", (hash_token(manage_token), existing["id"]))
                msg = emailer.already_registered_email(clean["email"], f"{settings.base_url}/manage/{manage_token}")
            else:
                verify_token = new_token()
                conn.execute(
                    "UPDATE contacts SET verify_token_hash = ?, manage_token_hash = ? WHERE id = ?",
                    (hash_token(verify_token), hash_token(manage_token), existing["id"]),
                )
                msg = emailer.verification_email(
                    clean["email"], f"{settings.base_url}/verify/{verify_token}", f"{settings.base_url}/manage/{manage_token}"
                )
            background.add_task(emailer.send, msg)
            return RedirectResponse("/thanks", status_code=303)

        contact_id, profile_id = new_id(), new_id()
        verify_token, manage_token = new_token(), new_token()
        conn.execute(
            "INSERT INTO contacts (id, email, phone, verify_token_hash, manage_token_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (contact_id, clean["email"], clean["phone"], hash_token(verify_token), hash_token(manage_token), created),
        )
        conn.execute(
            """INSERT INTO profiles (id, contact_id, postal_code, postal_prefix, radius_km, for_whom, household_size,
                   age_band, language, time_without_doctor, ohip_status, hcc_registered, need_flags, health_consent,
                   feedback_consent, referral_source, status, created_at, last_active_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (
                profile_id, contact_id, clean["postal_code"], clean["postal_code"][:3], int(clean["radius_km"]),
                clean["for_whom"], clean["household_size"], clean["age_band"], clean["language"],
                clean["time_without_doctor"], clean["ohip_status"], clean["hcc_registered"],
                ",".join(clean["need_flags"]), int(clean["health_consent"]), int(clean["feedback_consent"]),
                clean["referral_source"], created, created,
            ),
        )
        scopes = ["service"] + (["health"] if clean["health_consent"] else []) + (["feedback"] if clean["feedback_consent"] else [])
        conn.execute(
            "INSERT INTO consent_log (contact_id, consent_version, scopes, created_at) VALUES (?, ?, ?, ?)",
            (contact_id, settings.consent_version, ",".join(scopes), created),
        )

    msg = emailer.verification_email(
        clean["email"], f"{settings.base_url}/verify/{verify_token}", f"{settings.base_url}/manage/{manage_token}"
    )
    background.add_task(emailer.send, msg)
    return RedirectResponse("/thanks", status_code=303)


@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    return render(request, "thanks.html")


# ------------------------------------------------- email links (two-step: open, then click)


def contact_by_verify_token(conn, token: str):
    return conn.execute("SELECT * FROM contacts WHERE verify_token_hash = ?", (hash_token(token),)).fetchone()


@app.get("/verify/{token}", response_class=HTMLResponse)
def verify_page(request: Request, token: str):
    with transaction() as conn:
        contact = contact_by_verify_token(conn, token)
    if not contact:
        return render(request, "message.html", status_code=404, title="This link has expired",
                      body="This confirmation link is no longer valid. If you already confirmed, you are all set. "
                           "Otherwise, sign up again and we will send a new link.")
    return render(request, "confirm.html", action=f"/verify/{token}", title="Confirm your email",
                  body="Click the button to confirm your email and join the list.", button="Confirm my email")


@app.post("/verify/{token}")
def verify_submit(request: Request, token: str):
    stamp = now_iso()
    with transaction() as conn:
        contact = contact_by_verify_token(conn, token)
        if not contact:
            raise HTTPException(status_code=404)
        conn.execute("UPDATE contacts SET verified_at = ?, verify_token_hash = NULL WHERE id = ?", (stamp, contact["id"]))
        profile = conn.execute("SELECT postal_prefix FROM profiles WHERE contact_id = ?", (contact["id"],)).fetchone()
        conn.execute(
            "UPDATE profiles SET status = 'active', verified_at = ?, last_active_at = ? WHERE contact_id = ? AND status = 'pending'",
            (stamp, stamp, contact["id"]),
        )
        if profile:
            conn.execute(
                """INSERT INTO monthly_counts (month, postal_prefix, signups) VALUES (?, ?, 1)
                   ON CONFLICT(month, postal_prefix) DO UPDATE SET signups = signups + 1""",
                (stamp[:7], profile["postal_prefix"]),
            )
    return RedirectResponse("/verified", status_code=303)


@app.get("/verified", response_class=HTMLResponse)
def verified(request: Request):
    return render(request, "message.html", title="You are on the list",
                  body="Thanks for confirming. We will email you when a family practice near you tells us it has room. "
                       "Please also register with Health Care Connect if you have not already.",
                  show_hcc=True)


def load_manage(conn, token: str):
    contact = conn.execute("SELECT * FROM contacts WHERE manage_token_hash = ?", (hash_token(token),)).fetchone()
    if not contact:
        return None, None
    profile = conn.execute("SELECT * FROM profiles WHERE contact_id = ?", (contact["id"],)).fetchone()
    return contact, profile


@app.get("/manage/{token}", response_class=HTMLResponse)
def manage_page(request: Request, token: str):
    with transaction() as conn:
        contact, profile = load_manage(conn, token)
    if not contact:
        return render(request, "message.html", status_code=404, title="This link has expired",
                      body=f"This link is no longer valid. To change or delete your details, email {settings.org_contact_email}.")
    return render(request, "manage.html", token=token, contact=contact, profile=profile)


@app.post("/manage/{token}/keep")
def manage_keep(token: str):
    with transaction() as conn:
        contact, profile = load_manage(conn, token)
        if not contact or not profile:
            raise HTTPException(status_code=404)
        conn.execute("UPDATE profiles SET last_active_at = ?, reminder_sent_at = NULL WHERE id = ?", (now_iso(), profile["id"]))
    return RedirectResponse(f"/manage/{token}?done=keep", status_code=303)


@app.post("/manage/{token}/connected")
def manage_connected(request: Request, token: str):
    stamp = now_iso()
    with transaction() as conn:
        contact, profile = load_manage(conn, token)
        if not contact or not profile:
            raise HTTPException(status_code=404)
        if profile["feedback_consent"]:
            conn.execute("UPDATE profiles SET status = 'connected', connected_at = ? WHERE id = ?", (stamp, profile["id"]))
        else:
            # No follow-up agreed, so there is no reason to keep contact details.
            conn.execute("UPDATE profiles SET connected_at = ? WHERE id = ?", (stamp, profile["id"]))
            deidentify(conn, profile["id"], stamp)
    return render(request, "message.html", title="Congratulations",
                  body="We are glad you found a family doctor. We have taken you off the list and will not email you about openings.")


@app.post("/manage/{token}/delete")
def manage_delete(request: Request, token: str):
    with transaction() as conn:
        contact, _ = load_manage(conn, token)
        if not contact:
            raise HTTPException(status_code=404)
        delete_person(conn, contact["id"])
    return render(request, "message.html", title="Your data has been deleted",
                  body="We have deleted your email, phone number and answers. You will not hear from us again.")


# ---------------------------------------------------------------- admin


def require_admin(credentials: HTTPBasicCredentials | None = Depends(basic_auth)):
    if not settings.admin_password:
        raise HTTPException(status_code=404)
    ok = credentials is not None and secrets.compare_digest(credentials.username, settings.admin_user) and \
        secrets.compare_digest(credentials.password, settings.admin_password)
    if not ok:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


def suppress(count: int) -> str:
    return f"<{settings.min_cell_size}" if 0 < count < settings.min_cell_size else str(count)


def aggregate() -> dict:
    with transaction() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM profiles").fetchall()]
    active = [r for r in rows if r["status"] == "active"]

    def counts(field, options):
        c = Counter(r[field] for r in active if r[field])
        return [(q.label_for(options, k), suppress(v)) for k, v in c.most_common()]

    flag_counter = Counter()
    for r in active:
        for flag in filter(None, (r["need_flags"] or "").split(",")):
            flag_counter[flag] += 1
    flag_labels = {k: label for k, _, label in q.NEED_FLAGS}

    by_prefix = Counter(r["postal_prefix"] for r in active)
    weekly = Counter()
    for r in rows:
        if r["verified_at"]:
            week = datetime.fromisoformat(r["verified_at"]).strftime("%G-W%V")
            weekly[week] += 1

    return {
        "totals": {
            "Active (confirmed, still looking)": len(active),
            "Waiting for email confirmation": sum(r["status"] == "pending" for r in rows),
            "Connected": sum(r["status"] == "connected" for r in rows),
            "De-identified": sum(r["status"] == "deidentified" for r in rows),
        },
        "by_prefix": [(k, suppress(v)) for k, v in by_prefix.most_common()],
        "age": counts("age_band", q.AGE_BAND_OPTIONS),
        "gap": counts("time_without_doctor", q.TIME_WITHOUT_DOCTOR_OPTIONS),
        "ohip": counts("ohip_status", q.OHIP_OPTIONS),
        "hcc": counts("hcc_registered", q.HCC_OPTIONS),
        "language": counts("language", q.LANGUAGE_OPTIONS),
        "referral": counts("referral_source", q.REFERRAL_OPTIONS),
        "flags": [(flag_labels.get(k, k), suppress(v)) for k, v in flag_counter.most_common()],
        "health_consent": suppress(sum(1 for r in active if r["health_consent"])),
        "weekly": sorted(weekly.items())[-12:],
    }


@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def admin(request: Request):
    return render(request, "admin.html", data=aggregate())


@app.get("/admin/export.csv", dependencies=[Depends(require_admin)])
def admin_export():
    """Active demand by postal prefix and age band. Counts only, small cells suppressed."""
    with transaction() as conn:
        rows = conn.execute(
            """SELECT postal_prefix, age_band, COUNT(*) AS n,
                      SUM(CASE WHEN need_flags != '' THEN 1 ELSE 0 END) AS with_needs
               FROM profiles WHERE status = 'active' GROUP BY postal_prefix, age_band ORDER BY postal_prefix, age_band"""
        ).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["postal_prefix", "age_band", "active_signups", "with_any_need_flag"])
    for r in rows:
        writer.writerow([r["postal_prefix"], r["age_band"] or "", suppress(r["n"]), suppress(r["with_needs"] or 0)])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="demand-{stamp}.csv"'})
