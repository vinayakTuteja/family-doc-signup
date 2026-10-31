"""Runtime settings, read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "OpenPanel"))
    base_url: str = field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000").rstrip("/"))
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "data/signup.db"))

    # Sender identification required by CASL in every message we send.
    org_legal_name: str = field(default_factory=lambda: os.getenv("ORG_LEGAL_NAME", "OpenPanel (working name)"))
    org_mailing_address: str = field(default_factory=lambda: os.getenv("ORG_MAILING_ADDRESS", "Mailing address to be added, Toronto, ON"))
    org_contact_email: str = field(default_factory=lambda: os.getenv("ORG_CONTACT_EMAIL", "privacy@example.com"))

    # Email delivery. EMAIL_BACKEND=console writes messages to the log and to OUTBOX_DIR.
    email_backend: str = field(default_factory=lambda: os.getenv("EMAIL_BACKEND", "console"))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", "OpenPanel <hello@example.com>"))
    smtp_starttls: bool = field(default_factory=lambda: _bool("SMTP_STARTTLS", True))
    outbox_dir: str = field(default_factory=lambda: os.getenv("OUTBOX_DIR", "data/outbox"))

    # Admin dashboard (HTTP Basic auth). Leave ADMIN_PASSWORD empty to disable the dashboard.
    admin_user: str = field(default_factory=lambda: os.getenv("ADMIN_USER", "admin"))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))

    # Counts below this are shown as "<N" in the dashboard and exports.
    min_cell_size: int = field(default_factory=lambda: int(os.getenv("MIN_CELL_SIZE", "5")))

    # Basic abuse protection for the signup form.
    rate_limit_per_10min: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_10MIN", "5")))

    # Run the daily retention job inside the web server. Turn off if you schedule scripts/retention.py instead.
    run_retention_in_app: bool = field(default_factory=lambda: _bool("RUN_RETENTION_IN_APP", True))

    # Local testing only: shows saved emails at /dev/outbox. Never turn on in production.
    dev_mode: bool = field(default_factory=lambda: _bool("DEV_MODE", False))

    # Version of the consent wording shown on the form. Bump it whenever the wording changes.
    consent_version: str = field(default_factory=lambda: os.getenv("CONSENT_VERSION", "2026-11-v1"))


settings = Settings()
