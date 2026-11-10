"""Normalization helpers used by every source and by deduplication."""

import math
import re
import unicodedata
from urllib.parse import urlparse

POSTAL_RE = re.compile(r"([ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z])\s?(\d[ABCEGHJ-NPRSTV-Z]\d)", re.I)
ONTARIO_FSA_LETTERS = set("KLMNP")

# Words that say what kind of place it is, not which place it is. Removed before comparing names.
NAME_NOISE = {
    "dr", "drs", "doctor", "doctors", "md", "mbbs", "ccfp", "fcfp", "phd", "inc", "ltd", "limited", "corp",
    "professional", "corporation", "pc", "the", "and", "of", "at",
    "clinic", "clinics", "medical", "medicine", "centre", "center", "centres", "centers", "health", "healthcare",
    "care", "family", "practice", "physician", "physicians", "office", "offices", "group", "associates",
    "walk", "in", "walkin", "primary", "general", "team", "fht", "chc", "site", "location", "suite", "unit",
}

# Hosts shared by many unrelated businesses: a match on these says nothing.
GENERIC_HOSTS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com", "google.com", "goo.gl",
    "business.site", "linktr.ee", "yelp.com", "yelp.ca", "wix.com", "wixsite.com", "squarespace.com",
    "square.site", "godaddysites.com", "ratemds.com", "medimap.ca", "cortico.ca", "ocean.cognisantmd.com",
    "oceanmd.com", "janeapp.com", "maps.app.goo.gl", "youtube.com", "tiktok.com", "canada411.ca",
    "yellowpages.ca", "ontario.ca", "gov.on.ca", "findatopdoc.com", "healthgrades.com", "vitals.com",
    "zocdoc.com", "lumino.sunlife.ca", "sunlife.ca", "webmd.com", "doctor.webmd.com", "md.ca", "cpso.on.ca",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def postal_code(value: str | None) -> str:
    if not value:
        return ""
    m = POSTAL_RE.search(value.upper())
    return f"{m.group(1)} {m.group(2)}".upper() if m else ""


def is_ontario_postal(code: str) -> bool:
    return bool(code) and code[0] in ONTARIO_FSA_LETTERS


def phone(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return ""
    if digits[:3] in {"800", "833", "844", "855", "866", "877", "888"}:
        return ""  # toll-free numbers are usually shared call centres
    return digits


def email(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower().removeprefix("mailto:")
    return value if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", value) else ""


def website_key(value: str | None) -> str:
    """Domain (or domain + first path part for shared platforms) used to compare websites."""
    if not value:
        return ""
    v = value.strip()
    if "://" not in v:
        v = "http://" + v
    try:
        parsed = urlparse(v)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return ""
    if any(host == g or host.endswith("." + g) for g in GENERIC_HOSTS):
        return ""
    return host


def name_key(name: str) -> str:
    """Lower-case, no accents or punctuation, generic words removed. Used for fuzzy matching."""
    s = strip_accents(name or "").lower()
    s = s.replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t not in NAME_NOISE]
    return " ".join(tokens)


def street_key(address: str) -> str:
    """House number + first street word, e.g. '123 queen'. Units and suites are ignored."""
    s = strip_accents(address or "").lower()
    s = re.sub(r"\b(suite|ste|unit|apt|room|rm|floor|fl)\b\.?\s*#?\s*\w+", " ", s)
    s = re.sub(r"#\s*\w+", " ", s)
    s = re.sub(r"^\s*\w+\s*-\s*(?=\d)", "", s)  # "201-123 Main St" -> "123 Main St"
    m = re.search(r"\b(\d+[a-z]?)\s+([a-z]+)", s)
    return f"{m.group(1)} {m.group(2)}" if m else ""


def distance_m(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return math.inf
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
