import email
import glob
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import scoring
from app.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "outbox_dir", str(tmp_path / "outbox"))
    monkeypatch.setattr(settings, "admin_password", "secret")
    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(settings, "run_retention_in_app", False)
    from app import main

    main.rate_limiter.reset()
    with TestClient(main.app) as c:
        yield c


def db():
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def outbox():
    msgs = []
    for path in sorted(glob.glob(os.path.join(settings.outbox_dir, "*.eml"))):
        with open(path, "rb") as f:
            msgs.append(email.message_from_bytes(f.read()))
    return msgs


def text_of(msg):
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode()
    return ""


def link(msg, kind):
    match = re.search(rf"{settings.base_url}/{kind}/[A-Za-z0-9_\-]+", text_of(msg))
    assert match, f"no {kind} link in email"
    return match.group(0).replace(settings.base_url, "")


VALID = {
    "email": "Person@Example.com",
    "phone": "(416) 555-0199",
    "postal_code": "m5v3l9",
    "radius_km": "5",
    "for_whom": "self",
    "household_size": "2",
    "split_household": "yes",
    "age_band": "18_64",
    "language": "pa",
    "time_without_doctor": "2_5y",
    "ohip_status": "yes",
    "hcc_registered": "no",
    "need_flags": ["ongoing_condition", "newcomer"],
    "health_consent": "yes",
    "service_consent": "yes",
    "referral_source": "friend_family",
}


def signup(client, **overrides):
    data = {**VALID, **overrides}
    return client.post("/signup", data=data, follow_redirects=False)


def test_home_page_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "second job" in r.text and 'type="range"' in r.text
    assert "Health Care Connect" in r.text
    assert r.headers["Referrer-Policy"] == "no-referrer"


def test_signup_stores_contact_and_profile_separately(client):
    r = signup(client)
    assert r.status_code == 303 and r.headers["location"] == "/thanks"
    conn = db()
    contact = conn.execute("SELECT * FROM contacts").fetchone()
    profile = conn.execute("SELECT * FROM profiles").fetchone()
    assert contact["email"] == "person@example.com"
    assert contact["phone"] == "416-555-0199"
    assert profile["postal_code"] == "M5V 3L9"
    assert profile["postal_prefix"] == "M5V"
    assert profile["need_flags"] == "newcomer,ongoing_condition"
    assert profile["status"] == "pending"
    assert profile["radius_km"] == 5 and profile["split_household"] == "yes"
    assert "email" not in profile.keys()
    consent = conn.execute("SELECT * FROM consent_log").fetchone()
    assert consent["scopes"] == "service,health"


def test_need_flags_dropped_without_health_consent(client):
    r = signup(client, need_flags=[], health_consent="")
    assert r.status_code == 303
    assert db().execute("SELECT need_flags FROM profiles").fetchone()[0] == ""


def test_flags_without_consent_asks_user(client):
    r = signup(client, health_consent="")
    assert r.status_code == 422
    assert "Tick this box" in r.text


@pytest.mark.parametrize("field,value", [
    ("postal_code", "V6B 1A1"),   # British Columbia
    ("postal_code", "M5V"),
    ("email", "not-an-email"),
    ("phone", "12345"),
    ("radius_km", "100"),
    ("radius_km", "0"),
    ("radius_km", "abc"),
    ("split_household", ""),
    ("service_consent", ""),
])
def test_validation_errors(client, field, value):
    r = signup(client, **{field: value})
    assert r.status_code == 422
    assert db().execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0


def test_honeypot_silently_discards(client):
    r = signup(client, website="http://spam")
    assert r.status_code == 303
    assert db().execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0


def test_rate_limit(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main.rate_limiter, "limit", 2)
    signup(client, email="a@example.com")
    signup(client, email="b@example.com")
    r = signup(client, email="c@example.com")
    assert r.status_code == 429


def test_verification_is_two_step(client):
    signup(client)
    msgs = outbox()
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.get_content_type() == "multipart/alternative"
    assert "List-Unsubscribe" in msg
    assert settings.org_mailing_address in text_of(msg)
    verify = link(msg, "verify")

    # Opening the link (as an email security scanner would) changes nothing.
    r = client.get(verify)
    assert r.status_code == 200 and "Confirm my email" in r.text
    assert db().execute("SELECT status FROM profiles").fetchone()[0] == "pending"

    r = client.post(verify, follow_redirects=False)
    assert r.status_code == 303
    conn = db()
    assert conn.execute("SELECT status FROM profiles").fetchone()[0] == "active"
    assert conn.execute("SELECT signups FROM monthly_counts").fetchone()[0] == 1
    # Link is single use.
    assert client.get(verify).status_code == 404


def test_duplicate_signup_does_not_reveal_or_duplicate(client):
    signup(client)
    client.post(link(outbox()[0], "verify"))
    r = signup(client)
    assert r.status_code == 303 and r.headers["location"] == "/thanks"
    assert db().execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 1
    assert "already on our list" in text_of(outbox()[-1])


def test_manage_delete_removes_everything(client):
    signup(client)
    manage = link(outbox()[0], "manage")
    assert client.get(manage).status_code == 200
    r = client.post(f"{manage}/delete")
    assert r.status_code == 200
    conn = db()
    assert conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM consent_log").fetchone()[0] == 0


def test_connected_without_feedback_deidentifies_now(client):
    signup(client)
    msg = outbox()[0]
    client.post(link(msg, "verify"))
    client.post(f"{link(msg, 'manage')}/connected")
    conn = db()
    profile = conn.execute("SELECT * FROM profiles").fetchone()
    assert profile["status"] == "deidentified"
    assert profile["postal_code"] is None and profile["contact_id"] is None
    assert conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0


def test_connected_with_feedback_keeps_contact_90_days(client):
    from app import retention
    signup(client, feedback_consent="yes")
    msg = outbox()[0]
    client.post(link(msg, "verify"))
    client.post(f"{link(msg, 'manage')}/connected")
    assert db().execute("SELECT status FROM profiles").fetchone()[0] == "connected"
    retention.run(datetime.now(timezone.utc) + timedelta(days=91))
    assert db().execute("SELECT status FROM profiles").fetchone()[0] == "deidentified"


def test_retention_schedule(client):
    from app import retention
    now = datetime.now(timezone.utc)

    # Unconfirmed signups disappear after 7 days.
    signup(client, email="unconfirmed@example.com")
    retention.run(now + timedelta(days=8))
    assert db().execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0

    # Active signup: reminder at ~11 months, de-identified 30 days later with no reply.
    signup(client, email="active@example.com")
    client.post(link(outbox()[-1], "verify"))
    summary = retention.run(now + timedelta(days=340))
    assert summary["reminders_sent"] == 1
    assert "still looking" in text_of(outbox()[-1])
    summary = retention.run(now + timedelta(days=372))
    assert summary["inactive_deidentified"] == 1
    profile = db().execute("SELECT * FROM profiles").fetchone()
    assert profile["status"] == "deidentified" and profile["postal_prefix"] == "M5V"

    # De-identified records go after 24 months; monthly counts remain.
    retention.run(now + timedelta(days=372 + 731))
    conn = db()
    assert conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0
    assert conn.execute("SELECT SUM(signups) FROM monthly_counts").fetchone()[0] == 1


def test_still_looking_resets_timer(client):
    from app import retention
    now = datetime.now(timezone.utc)
    signup(client)
    client.post(link(outbox()[0], "verify"))
    retention.run(now + timedelta(days=340))
    keep = link(outbox()[-1], "manage")  # fresh link from the reminder
    client.post(f"{keep}/keep")
    summary = retention.run(now + timedelta(days=372))
    assert summary["inactive_deidentified"] == 0


def test_admin_requires_password(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401


def test_admin_shows_counts_not_contacts(client):
    signup(client)
    client.post(link(outbox()[0], "verify"))
    r = client.get("/admin", auth=("admin", "secret"))
    assert r.status_code == 200
    assert "person@example.com" not in r.text
    assert "&lt;5" in r.text  # small cells suppressed
    csv_r = client.get("/admin/export.csv", auth=("admin", "secret"))
    assert csv_r.status_code == 200
    assert "M5V,18_64,<5,<5" in csv_r.text


def test_admin_disabled_without_password(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")
    assert client.get("/admin", auth=("admin", "")).status_code == 404


def test_priority_score_rules():
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    healthy = scoring.priority_score(set(), "18_64", "lt_6m", now, now)
    assert healthy == 0
    # Clinical points are capped.
    many = scoring.priority_score(set(scoring.CLINICAL_POINTS), "18_64", "lt_6m", now, now)
    assert many == scoring.CLINICAL_CAP
    # Waiting raises everyone eventually.
    waited = scoring.priority_score(set(), "18_64", "lt_6m", now - timedelta(days=300), now)
    assert waited == 10
    ranked = scoring.rank([
        {"id": "early_healthy", "need_flags": set(), "age_band": "18_64", "time_without_doctor": "lt_6m", "verified_at": now - timedelta(days=60)},
        {"id": "late_infant", "need_flags": set(), "age_band": "under_2", "time_without_doctor": "lt_6m", "verified_at": now},
        {"id": "late_healthy", "need_flags": set(), "age_band": "18_64", "time_without_doctor": "lt_6m", "verified_at": now},
    ], now)
    assert [c["id"] for c in ranked] == ["late_infant", "early_healthy", "late_healthy"]


def test_dev_outbox_only_in_dev_mode(client, monkeypatch):
    signup(client)
    assert client.get("/dev/outbox").status_code == 404
    monkeypatch.setattr(settings, "dev_mode", True)
    r = client.get("/dev/outbox")
    assert r.status_code == 200
    assert "Confirm your email" in r.text and '<a href="http://localhost:8000/verify/' in r.text


def test_combined_need_and_barrier_bonus_and_rural():
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    clinical_only = scoring.priority_score({"ongoing_condition"}, "18_64", "lt_6m", now, now)
    barrier_only = scoring.priority_score({"no_transport"}, "18_64", "lt_6m", now, now)
    both = scoring.priority_score({"ongoing_condition", "no_transport"}, "18_64", "lt_6m", now, now)
    assert both == clinical_only + barrier_only + scoring.COMBINED_BONUS
    urban = scoring.priority_score({"ongoing_condition"}, "18_64", "lt_6m", now, now, postal_prefix="M5V")
    rural = scoring.priority_score({"ongoing_condition"}, "18_64", "lt_6m", now, now, postal_prefix="K0K")
    assert rural == urban + scoring.RURAL_POINTS + scoring.COMBINED_BONUS
    # Access points are capped.
    all_access = scoring.priority_score(set(scoring.ACCESS_POINTS), "18_64", "lt_6m", now, now)
    assert all_access == scoring.ACCESS_CAP


def test_every_need_flag_has_a_weight():
    from app import questions as q
    weighted = set(scoring.CLINICAL_POINTS) | set(scoring.ACCESS_POINTS)
    assert q.NEED_FLAG_KEYS == weighted
