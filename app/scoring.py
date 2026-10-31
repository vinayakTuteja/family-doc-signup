"""Priority score used to decide who is offered a clinic opening first.

Not used by the signup page itself. It lives here so the rules are written down, tested
and can be published before matching starts. Rules in plain words:

* Clinical needs add points, capped so no single answer dominates.
* Access and social barriers add a smaller, capped number of points. Living in a rural
  area (postal codes whose second character is 0) counts as one barrier automatically.
* Having both a real clinical need and at least one barrier adds a bonus: the same
  condition is riskier when care is harder to reach.
* Infants and adults 75+ get extra points (allowed under the Ontario Human Rights Code:
  age protection covers adults 18+, and s. 15 permits preference for people 65+).
* Longer time without a family doctor adds points (objective and hard to game).
* Time spent waiting on our list adds a point every 30 days with no cap, so everyone
  eventually rises to the top. Ties go to whoever signed up first.
"""

from datetime import datetime, timezone

CLINICAL_POINTS = {
    "ongoing_condition": 3,
    "multiple_meds": 2,
    "immunocompromised": 3,
    "pregnancy": 3,
    "mental_health": 2,
    "recent_hospital": 3,
    "needs_followup": 3,
    "serious_illness": 4,
}
CLINICAL_CAP = 10

ACCESS_POINTS = {
    "newcomer": 1,
    "disability": 1,
    "language_barrier": 1,
    "no_transport": 1,
    "no_alternative_care": 1,
    "limited_support": 1,
    "unstable_housing": 2,
    "financial_hardship": 1,
}
RURAL_POINTS = 1
ACCESS_CAP = 4

# Need plus barrier: at least this many clinical points and at least one access point.
COMBINED_BONUS = 2
COMBINED_MIN_CLINICAL = 3

AGE_POINTS = {"under_2": 3, "2_17": 1, "18_64": 0, "65_74": 1, "75_plus": 3}

TIME_WITHOUT_DOCTOR_POINTS = {
    "lt_6m": 0,
    "6_12m": 1,
    "1_2y": 2,
    "2_5y": 3,
    "5y_plus": 4,
    "never": 2,
}

DAYS_PER_WAIT_POINT = 30


def is_rural(postal_prefix: str | None) -> bool:
    # Canada Post uses 0 as the second character for rural forward sortation areas.
    return bool(postal_prefix) and len(postal_prefix) >= 2 and postal_prefix[1] == "0"


def priority_score(
    need_flags: set[str],
    age_band: str | None,
    time_without_doctor: str | None,
    verified_at: datetime,
    now: datetime | None = None,
    postal_prefix: str | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    clinical = min(sum(CLINICAL_POINTS.get(flag, 0) for flag in need_flags), CLINICAL_CAP)
    access_raw = sum(ACCESS_POINTS.get(flag, 0) for flag in need_flags)
    if is_rural(postal_prefix):
        access_raw += RURAL_POINTS
    access = min(access_raw, ACCESS_CAP)
    combined = COMBINED_BONUS if clinical >= COMBINED_MIN_CLINICAL and access >= 1 else 0
    age = AGE_POINTS.get(age_band or "", 0)
    gap = TIME_WITHOUT_DOCTOR_POINTS.get(time_without_doctor or "", 0)
    waited_days = max((now - verified_at).days, 0)
    waiting = waited_days // DAYS_PER_WAIT_POINT
    return clinical + access + combined + age + gap + waiting


def rank(candidates: list[dict], now: datetime | None = None) -> list[dict]:
    """Sort candidates (dicts with need_flags, age_band, time_without_doctor, verified_at, postal_prefix)."""
    now = now or datetime.now(timezone.utc)

    def key(c):
        score = priority_score(c["need_flags"], c["age_band"], c["time_without_doctor"], c["verified_at"], now,
                               c.get("postal_prefix"))
        return (-score, c["verified_at"])

    return sorted(candidates, key=key)
