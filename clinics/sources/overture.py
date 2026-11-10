"""Overture Maps places (https://overturemaps.org).

Licence: per record (CDLA-Permissive-2.0, Apache-2.0 or CC0-1.0). No share-alike.
Read straight from Overture's public S3 bucket with DuckDB; no account needed.
"""

import logging
import re
import urllib.request

from ..normalize import email, phone, postal_code
from ..record import SourceRecord

log = logging.getLogger(__name__)

DEFAULT_RELEASE = "2026-10-21.0"
ONTARIO_BBOX = (-95.16, 41.66, -74.32, 56.86)  # xmin, ymin, xmax, ymax

# Overture taxonomy categories that can be a family practice. "health_care" is broad and noisy;
# the classifier decides what to keep.
CATEGORIES = [
    "family_practice",
    "primary_care_or_general_clinic",
    "walk_in_clinic",
    "doctors_office",
    "medical_center",
    "community_health_center",
    "public_health_clinic",
    "health_care",
    "internal_medicine",
    "urgent_care_clinic",
]


def latest_release() -> str:
    """Newest release folder in Overture's public bucket, or the pinned default if unreachable."""
    url = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/?list-type=2&prefix=release/&delimiter=/"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode()
        releases = sorted(re.findall(r"<Prefix>release/(\d{4}-\d{2}-\d{2}\.\d+)/</Prefix>", body))
        return releases[-1] if releases else DEFAULT_RELEASE
    except Exception:  # network trouble: fall back to the pinned release
        return DEFAULT_RELEASE


def query(release: str = DEFAULT_RELEASE) -> str:
    xmin, ymin, xmax, ymax = ONTARIO_BBOX
    cats = ", ".join(f"'{c}'" for c in CATEGORIES)
    src = f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
    return f"""
        SELECT id, names."primary" AS name, taxonomy."primary" AS category,
               ST_Y(geometry) AS lat, ST_X(geometry) AS lon,
               addresses, phones, emails, websites, operating_status, confidence,
               sources[1].license AS licence
        FROM read_parquet('{src}', hive_partitioning=1)
        WHERE bbox.xmin BETWEEN {xmin} AND {xmax} AND bbox.ymin BETWEEN {ymin} AND {ymax}
          AND taxonomy."primary" IN ({cats})
          AND (operating_status IS NULL OR operating_status = 'open')
    """


def load(release: str | None = None) -> list[SourceRecord]:
    import duckdb  # imported here so the web app does not need it

    release = release or latest_release()
    log.info("Overture release %s", release)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2'; SET enable_progress_bar=false;")
    rows = con.execute(query(release)).fetchall()
    cols = [d[0] for d in con.description]
    records = []
    for row in rows:
        r = dict(zip(cols, row))
        addr = (r["addresses"] or [{}])[0] or {}
        region = (addr.get("region") or "").upper()
        pc = postal_code(addr.get("postcode"))
        # Keep Ontario only: the bounding box also covers parts of Quebec, Manitoba and the US.
        if region not in {"ON", "ONTARIO"} and not (pc and pc[0] in "KLMNP"):
            continue
        records.append(SourceRecord(
            source="overture",
            source_id=r["id"],
            licence=r["licence"] or "CDLA-Permissive-2.0",
            name=r["name"] or "",
            lat=r["lat"], lon=r["lon"],
            address=addr.get("freeform") or "",
            city=addr.get("locality") or "",
            postal_code=pc,
            phones=[p for p in (phone(x) for x in (r["phones"] or [])) if p],
            emails=[e for e in (email(x) for x in (r["emails"] or [])) if e],
            websites=list(r["websites"] or []),
            category=r["category"] or "",
        ))
    log.info("Overture: %d Ontario records", len(records))
    return records
