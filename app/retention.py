"""Data retention, run daily (see scripts/retention.py).

Schedule, matching the privacy notice:
1. Unconfirmed signups are deleted after 7 days.
2. Active signups get a "still looking?" email after 11 months without activity, and
   are de-identified if they do not respond within 30 days.
3. People marked connected are de-identified after 90 days (immediately if they did
   not agree to a follow-up).
4. De-identified records are deleted after 24 months. Monthly counts are kept.

De-identifying deletes the email and phone and the full postal code. What remains is the
postal prefix, age band, answers and dates, which we still protect as personal
information until it is deleted.
"""

import logging
from datetime import datetime, timedelta, timezone

from . import emailer
from .config import settings
from .db import transaction
from .security import hash_token, new_token

log = logging.getLogger("retention")

UNVERIFIED_DAYS = 7
REMINDER_AFTER_DAYS = 335  # about 11 months
REMINDER_GRACE_DAYS = 30
CONNECTED_DAYS = 90
DEIDENTIFIED_DAYS = 730


def deidentify(conn, profile_id: str, now_iso: str) -> None:
    row = conn.execute("SELECT contact_id FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if row and row["contact_id"]:
        conn.execute("DELETE FROM contacts WHERE id = ?", (row["contact_id"],))
    conn.execute(
        "UPDATE profiles SET contact_id = NULL, postal_code = NULL, status = 'deidentified', deidentified_at = ? WHERE id = ?",
        (now_iso, profile_id),
    )


def delete_person(conn, contact_id: str) -> None:
    conn.execute("DELETE FROM profiles WHERE contact_id = ?", (contact_id,))
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    summary = {"unverified_deleted": 0, "reminders_sent": 0, "inactive_deidentified": 0,
               "connected_deidentified": 0, "old_records_deleted": 0}
    outgoing = []

    with transaction() as conn:
        # 1. Unconfirmed signups.
        cutoff = (now - timedelta(days=UNVERIFIED_DAYS)).isoformat(timespec="seconds")
        for row in conn.execute(
            "SELECT contact_id FROM profiles WHERE status = 'pending' AND created_at < ?", (cutoff,)
        ).fetchall():
            delete_person(conn, row["contact_id"])
            summary["unverified_deleted"] += 1

        # 2a. Reminder for long-inactive active signups.
        cutoff = (now - timedelta(days=REMINDER_AFTER_DAYS)).isoformat(timespec="seconds")
        rows = conn.execute(
            """SELECT p.id, c.id AS contact_id, c.email FROM profiles p JOIN contacts c ON c.id = p.contact_id
               WHERE p.status = 'active' AND p.last_active_at < ? AND p.reminder_sent_at IS NULL""",
            (cutoff,),
        ).fetchall()
        for row in rows:
            token = new_token()  # fresh manage link, since we only store hashes
            conn.execute("UPDATE contacts SET manage_token_hash = ? WHERE id = ?", (hash_token(token), row["contact_id"]))
            conn.execute("UPDATE profiles SET reminder_sent_at = ? WHERE id = ?", (now_iso, row["id"]))
            outgoing.append(emailer.still_looking_email(row["email"], f"{settings.base_url}/manage/{token}"))
            summary["reminders_sent"] += 1

        # 2b. No response to the reminder.
        cutoff = (now - timedelta(days=REMINDER_GRACE_DAYS)).isoformat(timespec="seconds")
        for row in conn.execute(
            """SELECT id FROM profiles WHERE status = 'active' AND reminder_sent_at IS NOT NULL
               AND reminder_sent_at < ? AND last_active_at <= reminder_sent_at""",
            (cutoff,),
        ).fetchall():
            deidentify(conn, row["id"], now_iso)
            summary["inactive_deidentified"] += 1

        # 3. Connected.
        cutoff = (now - timedelta(days=CONNECTED_DAYS)).isoformat(timespec="seconds")
        for row in conn.execute(
            "SELECT id FROM profiles WHERE status = 'connected' AND connected_at < ?", (cutoff,)
        ).fetchall():
            deidentify(conn, row["id"], now_iso)
            summary["connected_deidentified"] += 1

        # 4. Old de-identified records.
        cutoff = (now - timedelta(days=DEIDENTIFIED_DAYS)).isoformat(timespec="seconds")
        cur = conn.execute(
            "DELETE FROM profiles WHERE status = 'deidentified' AND deidentified_at < ?", (cutoff,)
        )
        summary["old_records_deleted"] = cur.rowcount

    for msg in outgoing:
        try:
            emailer.send(msg)
        except Exception:  # keep going; the reminder can be resent manually
            log.exception("Failed to send reminder to %s", msg["To"])

    log.info("Retention run: %s", summary)
    return summary
