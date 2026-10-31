"""SQLite storage.

Contact details (email, phone) live in their own table, separate from the profile
(location and answers). Profiles point to contacts by a random ID. De-identifying a
person deletes the contact row and trims the profile, so what is left cannot be used to
reach them.
"""

import os
import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    verify_token_hash TEXT,
    manage_token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
    postal_code TEXT,              -- full code while active; NULL once de-identified
    postal_prefix TEXT NOT NULL,   -- first 3 characters (forward sortation area)
    radius_km INTEGER NOT NULL,
    for_whom TEXT NOT NULL,
    household_size INTEGER,
    age_band TEXT,
    language TEXT,
    time_without_doctor TEXT,
    ohip_status TEXT NOT NULL,
    hcc_registered TEXT NOT NULL,
    need_flags TEXT NOT NULL DEFAULT '',   -- comma-separated keys, empty without health consent
    health_consent INTEGER NOT NULL DEFAULT 0,
    feedback_consent INTEGER NOT NULL DEFAULT 0,
    referral_source TEXT,
    status TEXT NOT NULL,          -- pending | active | connected | deidentified
    created_at TEXT NOT NULL,
    verified_at TEXT,
    last_active_at TEXT NOT NULL,
    reminder_sent_at TEXT,
    connected_at TEXT,
    deidentified_at TEXT
);

CREATE TABLE IF NOT EXISTS consent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    consent_version TEXT NOT NULL,
    scopes TEXT NOT NULL,          -- comma-separated: service, health, feedback
    created_at TEXT NOT NULL
);

-- Monthly roll-up kept after individual profiles are deleted. Counts only.
CREATE TABLE IF NOT EXISTS monthly_counts (
    month TEXT NOT NULL,
    postal_prefix TEXT NOT NULL,
    signups INTEGER NOT NULL,
    PRIMARY KEY (month, postal_prefix)
);

CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_contact ON profiles(contact_id);
"""


def connect() -> sqlite3.Connection:
    path = settings.database_path
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
