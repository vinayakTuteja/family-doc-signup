"""Priority score used to decide who is offered a clinic opening first.

Not used by the signup page itself. It lives here so the rules are written down, tested
and can be published before matching starts. Rules in plain words:

* Clinical needs add points, capped so no single answer dominates.
* Access and social barriers add a smaller, capped number of points.
* Infants and adults 75+ get extra points (allowed under the Ontario Human Rights Code:
  age protection covers adults 18+, and s. 15 permits preference for people 65+).
* Longer time without a family doctor adds points (objective and hard to game).
* Time spent waiting on our list adds a point every 30 days with no cap, so everyone
  eventually rises to the top. Ties go to whoever signed up first.
"""

from datetime import datetime, timezone

CLINICAL_POINTS = {
    "ongoing_condition": 3,
    "immunocompromised": 3,
    "pregnancy": 3,
    "mental_health": 2,
    "recent_hospital": 3,
    "serious_illness": 4,
}
CLINICAL_CAP = 8

ACCESS_POINTS = {
    "newcomer": 1,
    "disability": 1,
    "language_barrier": 1,
    "no_transport": 1,
    "unstable_housing": 1,
}
ACCESS_CAP = 3

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


def priority_score(
    need_flags: set[str],
    age_band: str | None,
    time_without_doctor: str | None,
    verified_at: datetime,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    clinical = min(sum(CLINICAL_POINTS.get(flag, 0) for flag in need_flags), CLINICAL_CAP)
    access = min(sum(ACCESS_POINTS.get(flag, 0) for flag in need_flags), ACCESS_CAP)
    age = AGE_POINTS.get(age_band or "", 0)
    gap = TIME_WITHOUT_DOCTOR_POINTS.get(time_without_doctor or "", 0)
    waited_days = max((now - verified_at).days, 0)
    waiting = waited_days // DAYS_PER_WAIT_POINT
    return clinical + access + age + gap + waiting


def rank(candidates: list[dict], now: datetime | None = None) -> list[dict]:
    """Sort candidates (dicts with need_flags, age_band, time_without_doctor, verified_at)."""
    now = now or datetime.now(timezone.utc)

    def key(c):
        score = priority_score(c["need_flags"], c["age_band"], c["time_without_doctor"], c["verified_at"], now)
        return (-score, c["verified_at"])

    return sorted(candidates, key=key)
