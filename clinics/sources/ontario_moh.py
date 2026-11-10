"""Ontario Ministry of Health Service Provider Locations (MOHSERLO).

Licence: Open Government Licence – Ontario. Attribution: "Contains information licensed under
the Open Government Licence – Ontario." Covers team-based primary care sites only.
"""

import json
import logging
import urllib.parse
import urllib.request

from ..normalize import postal_code
from ..record import SourceRecord

log = logging.getLogger(__name__)

SERVICE_URL = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open09/MapServer/26/query"
)

# Service types that are primary care. Nurse practitioner-led clinics and nursing stations have
# no family physicians, but they take unattached patients, so they are kept and labelled.
PRIMARY_CARE_TYPES = [
    "Family Health Team",
    "Community Health Centre",
    "Indigenous Primary Health Care Organization",
    "Nurse Practitioner-Led Clinic",
    "Nursing Station",
]

PAGE_SIZE = 1000


def fetch_page(offset: int) -> dict:
    types = ", ".join("'" + t.replace("'", "''") + "'" for t in PRIMARY_CARE_TYPES)
    params = {
        "where": f"SERVICE_TYPE IN ({types})",
        "outFields": "MOH_SERVICE_PROVIDER_IDENT,SERVICE_TYPE,SERVICE_TYPE_DETAIL,ENGLISH_NAME,"
                     "ADDRESS_LINE_1,ADDRESS_LINE_2,COMMUNITY,POSTAL_CODE,OBJECTID",
        "returnGeometry": "true",
        "outSR": "4326",
        "orderByFields": "OBJECTID",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "f": "json",
    }
    url = SERVICE_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def parse(features: list[dict]) -> list[SourceRecord]:
    records = []
    for f in features:
        a = f.get("attributes", {})
        g = f.get("geometry") or {}
        address = " ".join(x for x in (a.get("ADDRESS_LINE_1"), a.get("ADDRESS_LINE_2")) if x)
        records.append(SourceRecord(
            source="ontario_moh",
            source_id=str(a.get("MOH_SERVICE_PROVIDER_IDENT") or a.get("OBJECTID")),
            licence="OGL-Ontario",
            name=(a.get("ENGLISH_NAME") or "").strip(),
            lat=g.get("y"), lon=g.get("x"),
            address=address,
            city=(a.get("COMMUNITY") or "").title(),
            postal_code=postal_code(a.get("POSTAL_CODE")),
            category=a.get("SERVICE_TYPE") or "",
            raw_type=a.get("SERVICE_TYPE_DETAIL") or "",
        ))
    return records


def load() -> list[SourceRecord]:
    records, offset = [], 0
    while True:
        page = fetch_page(offset)
        if "error" in page:
            raise RuntimeError(f"Ontario MOH service error: {page['error']}")
        features = page.get("features", [])
        records.extend(parse(features))
        if len(features) < PAGE_SIZE and not page.get("exceededTransferLimit"):
            break
        offset += len(features)
    log.info("Ontario MOH: %d primary care sites", len(records))
    return records
