"""OpenStreetMap via the Overpass API.

Licence: ODbL 1.0. Fine for internal use. If a database built from it is ever published, the
database must be shared under ODbL too, with attribution "© OpenStreetMap contributors".
"""

import json
import logging
import time
import urllib.parse
import urllib.request

from ..normalize import email, phone, postal_code
from ..record import SourceRecord

log = logging.getLogger(__name__)

# The main public Overpass server is busy at times; mirrors are tried in turn.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
ATTEMPTS_PER_SERVER = 2

QUERY = """
[out:json][timeout:300];
area["ISO3166-2"="CA-ON"][admin_level=4]->.on;
(
  nwr["amenity"="doctors"](area.on);
  nwr["healthcare"="doctor"](area.on);
  nwr["amenity"="clinic"](area.on);
  nwr["healthcare"="clinic"](area.on);
  nwr["healthcare"="centre"](area.on);
);
out center tags;
"""


def fetch() -> dict:
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    last_error = None
    for url in OVERPASS_URLS:
        for attempt in range(ATTEMPTS_PER_SERVER):
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "family-doc-signup/1.0"})
                with urllib.request.urlopen(req, timeout=400) as resp:
                    result = json.load(resp)
                if result.get("elements"):
                    return result
                last_error = RuntimeError(f"{url} returned no elements")
            except Exception as exc:  # busy server, timeout or bad gateway: wait and try again
                last_error = exc
                log.warning("Overpass %s attempt %d failed: %s", url, attempt + 1, exc)
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"All Overpass servers failed: {last_error}")


def parse(elements: list[dict]) -> list[SourceRecord]:
    records = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or ""
        if not name:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
        phones = [tags.get(k) for k in ("phone", "contact:phone") if tags.get(k)]
        phones = [p for raw in phones for p in (phone(x) for x in raw.split(";")) if p]
        emails = [e for e in (email(tags.get(k)) for k in ("email", "contact:email")) if e]
        websites = [tags.get(k) for k in ("website", "contact:website", "url") if tags.get(k)]
        category = tags.get("healthcare") or tags.get("amenity") or ""
        specialty = tags.get("healthcare:speciality", "")
        records.append(SourceRecord(
            source="osm",
            source_id=f"{el.get('type', 'node')}/{el.get('id')}",
            licence="ODbL-1.0",
            name=name,
            lat=lat, lon=lon,
            address=street,
            city=tags.get("addr:city", ""),
            postal_code=postal_code(tags.get("addr:postcode")),
            phones=phones, emails=emails, websites=websites,
            category=category,
            raw_type=specialty,
        ))
    return records


def load() -> list[SourceRecord]:
    records = parse(fetch().get("elements", []))
    log.info("OpenStreetMap: %d named records", len(records))
    return records
