"""Tokens, rate limiting and small helpers."""

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone


def new_id() -> str:
    return secrets.token_hex(16)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Only hashes are stored, so a database leak does not expose working links.
    return hashlib.sha256(token.encode()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class RateLimiter:
    """In-memory sliding window. Fine for a single small server; swap for Redis if scaled out."""

    def __init__(self, limit: int, window_seconds: int = 600):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self.hits.clear()
