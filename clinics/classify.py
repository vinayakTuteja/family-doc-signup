"""Decide whether a record is likely a family practice, and what kind.

Open map data mixes family practices with dentists, labs, spas and specialists. This keeps
anything that could plausibly take family practice patients and labels how sure we are, so a
person can review the uncertain ones. Rules are deliberately readable rather than clever.
"""

import re

from .record import SourceRecord

# Name words that mean "not a family practice". Checked as whole words or word starts.
HARD_EXCLUDE = [
    r"dent(al|ist|ure)", r"orthodont", r"endodont", r"periodont", r"\bsmile", r"physio", r"chiro", r"\bdc\b",
    r"massage", r"\brmt\b", r"optom", r"\beye\b", r"lasik", r"ophthalm", r"pharmacist", r"\bvet",
    r"animal", r"\bpet\b", r"naturopath", r"\bnd\b", r"acupunct", r"\bspa\b", r"esthetic", r"aesthetic",
    r"cosmetic", r"botox", r"laser", r"hearing", r"audiolog", r"podiatr", r"chiropod", r"\bfoot\b", r"\bfeet\b",
    r"orthotic", r"insole", r"psycholog", r"psychotherap", r"counsel", r"therapist", r"\btherapy\b", r"speech",
    r"\bmsw\b", r"\brsw\b", r"social work", r"cannabis", r"fertility", r"\bivf\b", r"sleep", r"dermatolog",
    r"derma", r"cardiolog", r"urolog", r"gastro", r"oncolog", r"allerg", r"plastic surg", r"weight loss", r"\bhair\b",
    r"ketamine", r"obstetric", r"gyna?ecolog", r"kidney", r"dialysis", r"insurance", r"home ?care",
    r"personal care", r"nursing agency", r"staffing", r"wellness rx", r"medical suppl", r"supplies", r"rental",
    r"breast pump", r"hijama", r"cupping", r"yoga", r"fitness", r"nutrition", r"dietit", r"hypnother", r"holistic",
    r"midwi", r"blood donor", r"blood services", r"occupational health", r"sports medicine", r"orthop",
    r"\bsurg(eon|ery|ical)?\b", r"\blice\b", r"licesquad", r"infusion", r"diabetes education", r"recruitment",
    r"vaccin", r"ambulance", r"paramedic", r"\bstudio\b", r"endoscop", r"research", r"\bvein", r"men'?s health",
    r"ob ?gyn", r"retirement", r"seniors village", r"long[- ]term care", r"rehab", r"kinesiolog",
]
# Words that usually mean "not a family practice", unless the name also clearly says it is one
# (e.g. "Oak Park Medical Clinic & Pharmacy", "St Michael's Hospital Academic Family Health Team").
SOFT_EXCLUDE = [
    r"pharm", r"drug ?mart", r"rexall", r"shoppers", r"\brx\b", r"\blabs?\b", r"laborator", r"lifelabs",
    r"dynacare", r"imaging", r"x-?ray", r"ultra ?sound", r"\bmri\b", r"radiolog", r"diagnostic", r"hospital",
    r"travel (clinic|medic)", r"\bvision\b", r"optical", r"\boptic",
]
HARD_EXCLUDE_RE = re.compile("|".join(HARD_EXCLUDE), re.I)
SOFT_EXCLUDE_RE = re.compile("|".join(SOFT_EXCLUDE), re.I)
STRONG_FAMILY_RE = re.compile(
    r"famil(y|le) (practice|medicine|physician|doctor|health)|walk[ -]?in|medical (clinic|centre|center)|"
    r"\bfht\b|health network|family health",
    re.I,
)
# For broad categories, the name must at least sound medical.
MEDICAL_NAME_RE = re.compile(
    r"\bdr\b|\bmd\b|doctor|medic|clinic|health|physician|famil|practice|soahac|aboriginal|indigenous|"
    r"nursing station|access cent", re.I)
BROAD_CATEGORIES = {"health_care", "public_health_clinic"}

FAMILY_SIGNAL_RE = re.compile(
    r"famil(y|le)|medical (centre|center|clinic|group|associates|arts|building)|health (centre|center)|"
    r"primary care|\bfht\b|\bchc\b|walk[ -]?in|general practi|\bgp\b|community health|nurse practitioner",
    re.I,
)
WALK_IN_RE = re.compile(r"walk[ -]?in|urgent care|after[ -]?hours", re.I)

OVERTURE_TIERS = {
    "family_practice": "high",
    "primary_care_or_general_clinic": "high",
    "community_health_center": "high",
    "walk_in_clinic": "high",
    "doctors_office": "medium",
    "medical_center": "medium",
    "urgent_care_clinic": "medium",
    "health_care": "low",
    "public_health_clinic": "low",
    "internal_medicine": "low",
}

OSM_FAMILY_SPECIALTIES = {"", "general", "family_medicine", "general_practice", "primary_care"}

RANK = {"high": 3, "medium": 2, "low": 1}


def classify(r: SourceRecord) -> tuple[str, str] | None:
    """Return (practice_type, confidence), or None to exclude the record."""
    name = r.name or ""

    if r.source == "ontario_moh":
        if r.category in {"Nurse Practitioner-Led Clinic", "Nursing Station"}:
            return "np_led", "high"
        return "team_based", "high"

    if HARD_EXCLUDE_RE.search(name):
        return None
    if SOFT_EXCLUDE_RE.search(name) and not STRONG_FAMILY_RE.search(name):
        return None
    if r.source == "overture" and r.category in BROAD_CATEGORIES and not MEDICAL_NAME_RE.search(name):
        return None

    if r.source == "osm":
        specialties = {s.strip() for s in (r.raw_type or "").split(";")}
        if not specialties & OSM_FAMILY_SPECIALTIES:
            return None
        confidence = "medium" if (r.category in {"doctor", "doctors"} or FAMILY_SIGNAL_RE.search(name)) else "low"
    else:
        confidence = OVERTURE_TIERS.get(r.category, "low")
        if FAMILY_SIGNAL_RE.search(name) and confidence != "high":
            confidence = "medium" if confidence == "low" else "high"

    if WALK_IN_RE.search(name) or r.category == "walk_in_clinic":
        return "walk_in", confidence
    if re.search(r"community health|\bchc\b|family health team|\bfht\b", name, re.I):
        return "team_based", confidence
    if re.search(r"nurse practitioner", name, re.I):
        return "np_led", confidence
    return "family_practice", confidence
