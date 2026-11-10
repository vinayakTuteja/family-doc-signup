"""Build the Ontario family practice site list from every free source.

Usage:
    python -m clinics.build                          # all sources, all of Ontario
    python -m clinics.build --fsa M4 M5 M6           # only these postal areas (prefix match)
    python -m clinics.build --sources overture ontario_moh
    python -m clinics.build --osm-file osm.json      # use a saved Overpass result instead of the API
    python -m clinics.build --decisions data/clinics/review_pairs.csv   # apply reviewed decisions

Writes to --out (default data/clinics/):
    sites.csv          one row per practice site, with sources and how records were merged
    review_pairs.csv   near-duplicates for a person to mark "same" or "different"
    excluded.csv       records dropped as not family practice (dentists, labs, spas...)
    summary.json       counts per source and step
    ATTRIBUTION.txt    licence notices for the data used
"""

import argparse
import csv
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone

from .classify import classify
from .dedupe import deduplicate
from .normalize import distance_m, is_ontario_postal
from .record import SourceRecord

log = logging.getLogger("clinics")

ALL_SOURCES = ["ontario_moh", "overture", "osm"]

ATTRIBUTION = """Data sources and licences

Ontario Ministry of Health Service Provider Locations (MOHSERLO)
  Contains information licensed under the Open Government Licence – Ontario.
  https://www.ontario.ca/page/open-government-licence-ontario

Overture Maps Foundation, Places theme
  Per-record licence (CDLA-Permissive-2.0, Apache-2.0 or CC0-1.0); see the "licences" column.
  https://docs.overturemaps.org/attribution/

OpenStreetMap
  © OpenStreetMap contributors. Open Database License (ODbL) 1.0.
  Internal use is fine. If a database built from this data is ever published or shared
  outside the organization, it must be offered under the ODbL as well.
  https://www.openstreetmap.org/copyright
"""


def load_sources(names: list[str], osm_file: str | None, overture_release: str | None) -> dict[str, list]:
    loaded: dict[str, list] = {}
    for name in names:
        try:
            if name == "ontario_moh":
                from .sources import ontario_moh
                loaded[name] = ontario_moh.load()
            elif name == "overture":
                from .sources import overture
                loaded[name] = overture.load(overture_release)
            elif name == "osm":
                from .sources import osm
                if osm_file:
                    with open(osm_file) as f:
                        loaded[name] = osm.parse(json.load(f).get("elements", []))
                else:
                    loaded[name] = osm.load()
        except Exception as exc:  # one source failing should not stop the others
            log.error("Source %s failed: %s", name, exc)
            loaded[name] = []
    return loaded


FSA_GUESS_MAX_M = 800
GUESS_GRID = 0.01  # degrees, about 1 km


def guess_missing_fsas(records: list[SourceRecord]) -> int:
    """Give records without a postal code the FSA of the nearest record that has one (within 800 m).

    Every loaded record is used as an anchor, including ones later excluded (a dentist next door
    still tells us the postal area). Returns how many FSAs were estimated.
    """
    grid: dict = {}
    for r in records:
        if r.postal_code and r.lat is not None and r.lon is not None:
            grid.setdefault((int(r.lat // GUESS_GRID), int(r.lon // GUESS_GRID)), []).append(r)
    guessed = 0
    for r in records:
        if r.postal_code or r.lat is None or r.lon is None:
            continue
        cx, cy = int(r.lat // GUESS_GRID), int(r.lon // GUESS_GRID)
        best, best_d = None, FSA_GUESS_MAX_M
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for anchor in grid.get((cx + dx, cy + dy), []):
                    d = distance_m(r.lat, r.lon, anchor.lat, anchor.lon)
                    if d < best_d:
                        best, best_d = anchor, d
        if best:
            r.fsa_guess = best.postal_code[:3]
            guessed += 1
    return guessed


def in_scope(rec: SourceRecord, fsa_prefixes: list[str]) -> bool:
    if rec.postal_code and not is_ontario_postal(rec.postal_code):
        return False
    if not fsa_prefixes:
        return True
    return bool(rec.fsa) and any(rec.fsa.startswith(p.upper()) for p in fsa_prefixes)


def read_decisions(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    decisions = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            verdict = (row.get("decision") or "").strip().lower()
            if verdict in {"same", "different"} and row.get("record_a") and row.get("record_b"):
                decisions[(row["record_a"], row["record_b"])] = verdict
    return decisions


def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        open(path, "w").close()
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run(sources: list[str], fsa_prefixes: list[str], out_dir: str, osm_file: str | None = None,
        overture_release: str | None = None, decisions_path: str | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    # Read decisions before outputs are overwritten (the review file may live in out_dir).
    decisions = read_decisions(decisions_path)
    loaded = load_sources(sources, osm_file, overture_release)
    fsas_guessed = guess_missing_fsas([r for records in loaded.values() for r in records])

    kept, excluded = [], []
    for name, records in loaded.items():
        for rec in records:
            if not in_scope(rec, fsa_prefixes):
                continue
            result = classify(rec)
            if result is None:
                excluded.append({"source": rec.source, "source_id": rec.source_id, "name": rec.name,
                                 "category": rec.category, "address": rec.address, "fsa": rec.fsa})
            else:
                kept.append((rec, *result))

    sites, review = deduplicate(kept, decisions)

    summary = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fsa_filter": fsa_prefixes or "all Ontario",
        "records_loaded": {k: len(v) for k, v in loaded.items()},
        "records_in_scope": len(kept) + len(excluded),
        "records_excluded_not_family_practice": len(excluded),
        "records_kept": len(kept),
        "sites_after_dedupe": len(sites),
        "duplicates_merged": len(kept) - len(sites),
        "review_pairs": len(review),
        "decisions_applied": len(decisions),
        "sites_by_type": dict(Counter(s["practice_type"] for s in sites)),
        "sites_by_confidence": dict(Counter(s["confidence"] for s in sites)),
        "sites_found_in_2_plus_sources": sum(1 for s in sites if ";" in s["sources"]),
        "sites_with_email": sum(1 for s in sites if s["emails"]),
        "sites_with_phone": sum(1 for s in sites if s["phones"]),
        "sites_with_website": sum(1 for s in sites if s["websites"]),
        "sites_without_postal_code": sum(1 for s in sites if not s["postal_code"]),
        "records_with_estimated_fsa": fsas_guessed,
        "sites_with_estimated_fsa": sum(1 for s in sites if s["fsa_source"] == "estimated"),
        "sites_without_any_fsa": sum(1 for s in sites if not s["fsa"]),
        "sources_failed_or_empty": [k for k, v in loaded.items() if not v],
    }

    write_csv(os.path.join(out_dir, "sites.csv"), sites)
    write_csv(os.path.join(out_dir, "review_pairs.csv"), review)
    write_csv(os.path.join(out_dir, "excluded.csv"), excluded)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(out_dir, "ATTRIBUTION.txt"), "w") as f:
        f.write(ATTRIBUTION)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", nargs="+", default=ALL_SOURCES, choices=ALL_SOURCES)
    parser.add_argument("--fsa", nargs="*", default=[], help="FSA prefixes to keep, e.g. M4 M5 or M5V")
    parser.add_argument("--out", default="data/clinics")
    parser.add_argument("--osm-file", help="saved Overpass JSON to use instead of calling the API")
    parser.add_argument("--overture-release", help="Overture release, e.g. 2026-10-21.0")
    parser.add_argument("--decisions", help="reviewed review_pairs.csv to apply")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    summary = run(args.sources, args.fsa, args.out, args.osm_file, args.overture_release, args.decisions)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
