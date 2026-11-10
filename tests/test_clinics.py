import csv
import json
import os

import pytest

pytest.importorskip("rapidfuzz")

from clinics import build, normalize as n  # noqa: E402
from clinics.classify import classify  # noqa: E402
from clinics.dedupe import deduplicate  # noqa: E402
from clinics.record import SourceRecord  # noqa: E402
from clinics.sources import ontario_moh, osm  # noqa: E402


def rec(source="overture", sid="1", name="Clinic", lat=43.65, lon=-79.38, address="", postal="M5V 1A1",
        phones=(), emails=(), websites=(), category="family_practice", raw_type=""):
    return SourceRecord(source=source, source_id=sid, licence="test", name=name, lat=lat, lon=lon,
                        address=address, postal_code=postal, phones=list(phones), emails=list(emails),
                        websites=list(websites), category=category, raw_type=raw_type)


def run_dedupe(records, decisions=None):
    classified = [(r, *classify(r)) for r in records]
    return deduplicate(classified, decisions)


# ---------------------------------------------------------------- normalize

def test_postal_and_phone_normalization():
    assert n.postal_code("m5v3l9") == "M5V 3L9"
    assert n.postal_code("Toronto ON M5V 3L9 Canada") == "M5V 3L9"
    assert n.postal_code("90210") == ""
    assert n.phone("+1 (416) 555-0199") == "4165550199"
    assert n.phone("1-800-555-0199") == ""  # toll-free: shared call centre
    assert n.phone("555-0199") == ""


def test_website_and_name_keys():
    assert n.website_key("https://www.SmithFamilyMedicine.ca/contact") == "smithfamilymedicine.ca"
    assert n.website_key("https://facebook.com/someclinic") == ""
    assert n.name_key("Dr. R.A. Klassen, MD - Family Practice") == "r a klassen"
    assert n.name_key("Klassen R A Dr") == "klassen r a"
    assert n.street_key("201-123 Queen St W") == "123 queen"
    assert n.street_key("123 Queen Street West, Suite 400") == "123 queen"


# ---------------------------------------------------------------- classify

def test_classify_excludes_non_family_practice():
    assert classify(rec(name="Smile Dental Centre")) is None
    assert classify(rec(name="LifeLabs Patient Service Centre", category="health_care")) is None
    assert classify(rec(name="Downtown X-Ray and Ultrasound", category="doctors_office")) is None
    assert classify(rec(source="osm", name="Dr. Lee", category="doctor", raw_type="dermatology")) is None


def test_classify_labels_types():
    assert classify(rec(source="ontario_moh", name="X NPLC", category="Nurse Practitioner-Led Clinic")) == ("np_led", "high")
    assert classify(rec(source="ontario_moh", name="X FHT", category="Family Health Team")) == ("team_based", "high")
    assert classify(rec(name="Queen West Walk-In Clinic", category="doctors_office"))[0] == "walk_in"
    assert classify(rec(name="Dr. Smith", category="doctors_office")) == ("family_practice", "medium")
    assert classify(rec(name="Harbour Medical Centre", category="health_care")) == ("family_practice", "medium")


# ---------------------------------------------------------------- dedupe

def test_same_email_in_same_fsa_merges():
    sites, _ = run_dedupe([
        rec(sid="a", name="Queen West Family Medicine", emails=["office@qwfm.ca"]),
        rec(source="osm", sid="b", name="QW Family Med", lat=43.6505, emails=["office@qwfm.ca"]),
    ])
    assert len(sites) == 1
    assert "same email" in sites[0]["match_reasons"]
    assert sites[0]["sources"] == "overture; osm"


def test_physician_name_order_and_initials_merge():
    sites, _ = run_dedupe([
        rec(sid="a", name="Klassen R A Dr", address="250 Main St", category="doctors_office"),
        rec(source="osm", sid="b", name="Dr. R.A. Klassen", address="250 Main Street, Unit 3", lat=43.6501,
            category="doctors"),
    ])
    assert len(sites) == 1


def test_chain_sites_sharing_a_phone_are_linked_not_merged():
    sites, _ = run_dedupe([
        rec(sid="a", name="Appletree Medical - Bank", address="1 Bank St", phones=["6135550100"]),
        rec(sid="b", name="Appletree Medical - Merivale", address="900 Merivale Rd", lat=43.70,
            phones=["6135550100"]),
    ])
    assert len(sites) == 2
    assert sites[0]["org_id"] and sites[0]["org_id"] == sites[1]["org_id"]


def test_branch_sites_with_same_name_at_different_addresses_stay_separate():
    sites, _ = run_dedupe([
        rec(source="ontario_moh", sid="1", name="Timmins Academic Family Health Team - Toke Street Site",
            address="123 Toke St", postal="P4N 1A1", category="Family Health Team", lat=48.47, lon=-81.33),
        rec(source="ontario_moh", sid="2", name="Timmins Academic Family Health Team - Fifth Avenue Site",
            address="77 Fifth Ave", postal="P4N 1A1", category="Family Health Team", lat=48.48, lon=-81.34),
    ])
    assert len(sites) == 2


def test_rural_fsa_alone_is_not_same_area():
    sites, review = run_dedupe([
        rec(sid="a", name="Grey Medical Clinic", postal="N0C 1A0", lat=44.20, lon=-80.60),
        rec(sid="b", name="Grey Medical Clinic", postal="N0C 1B0", lat=44.55, lon=-80.90),  # ~45 km away
    ])
    assert len(sites) == 2


def test_very_similar_names_nearby_merge_and_borderline_goes_to_review():
    sites, _ = run_dedupe([
        rec(sid="a", name="Harwood Medical Clinic"),
        rec(source="ontario_moh", sid="b", name="Harwood Medical Centre", lat=43.6502, category="Family Health Team"),
    ])
    assert len(sites) == 1 and sites[0]["name"] == "Harwood Medical Centre"  # MOH name preferred

    sites, review = run_dedupe([
        rec(sid="a", name="Bridges Community Health Centre (Fort Erie Site)", lat=43.65),
        rec(sid="b", name="Bridges Community Health Centre", lat=43.6504),
    ])
    assert len(sites) == 2 and len(review) == 1
    assert review[0]["record_a"] and review[0]["decision"] == ""


def test_reviewer_decisions_are_applied():
    records = [
        rec(sid="a", name="Bridges Community Health Centre (Fort Erie Site)", lat=43.65),
        rec(sid="b", name="Bridges Community Health Centre", lat=43.6504),
    ]
    sites, review = run_dedupe(records, {("overture:a", "overture:b"): "same"})
    assert len(sites) == 1 and "confirmed by a reviewer" in sites[0]["match_reasons"]
    sites, review = run_dedupe(records, {("overture:b", "overture:a"): "different"})
    assert len(sites) == 2 and not review


def test_site_ids_are_stable_between_runs():
    records = [rec(sid="a", name="Alpha Clinic"), rec(sid="b", name="Beta Clinic", lat=43.70)]
    ids_1 = sorted(s["site_id"] for s in run_dedupe(records)[0])
    ids_2 = sorted(s["site_id"] for s in run_dedupe(list(reversed(records)))[0])
    assert ids_1 == ids_2


# ---------------------------------------------------------------- source parsers

def test_osm_parser():
    elements = [
        {"type": "node", "id": 1, "lat": 43.6, "lon": -79.4, "tags": {
            "name": "Dr. Ana Silva", "amenity": "doctors", "healthcare:speciality": "general",
            "addr:housenumber": "12", "addr:street": "College St", "addr:postcode": "m5g1k2",
            "phone": "+1 416 555 0123; +1 416 555 0124", "email": "Office@Silva.ca"}},
        {"type": "way", "id": 2, "center": {"lat": 43.7, "lon": -79.5}, "tags": {"amenity": "clinic"}},  # no name
    ]
    records = osm.parse(elements)
    assert len(records) == 1
    r = records[0]
    assert r.postal_code == "M5G 1K2" and r.phones == ["4165550123", "4165550124"] and r.emails == ["office@silva.ca"]
    assert r.address == "12 College St" and r.source_id == "node/1"


def test_ontario_moh_parser():
    features = [{"attributes": {"MOH_SERVICE_PROVIDER_IDENT": "97", "SERVICE_TYPE": "Family Health Team",
                                "ENGLISH_NAME": "Four Counties Family Health Team ", "ADDRESS_LINE_1": "253A Main Street",
                                "COMMUNITY": "GLENCOE", "POSTAL_CODE": "N0L1M0"},
                 "geometry": {"x": -81.71, "y": 42.75}}]
    r = ontario_moh.parse(features)[0]
    assert r.name == "Four Counties Family Health Team" and r.postal_code == "N0L 1M0" and r.city == "Glencoe"
    assert r.lat == 42.75 and r.licence == "OGL-Ontario"


# ---------------------------------------------------------------- end to end

def test_build_writes_outputs_and_filters_by_fsa(tmp_path, monkeypatch):
    fake = {
        "ontario_moh": [rec(source="ontario_moh", sid="1", name="Queen FHT", category="Family Health Team",
                            postal="M5V 1A1")],
        "overture": [rec(sid="2", name="Queen Family Health Team", postal="M5V 1A1", lat=43.6501),
                     rec(sid="3", name="Ottawa Clinic", postal="K1P 1A1", lat=45.42, lon=-75.69),
                     rec(sid="4", name="Bright Smile Dental", postal="M5V 2B2")],
        "osm": [],
    }
    monkeypatch.setattr(build, "load_sources", lambda names, osm_file, release: {k: fake[k] for k in names})
    out = tmp_path / "out"
    summary = build.run(build.ALL_SOURCES, ["M5"], str(out))
    assert summary["records_in_scope"] == 3
    assert summary["records_excluded_not_family_practice"] == 1
    assert summary["sites_after_dedupe"] == 1
    assert summary["sources_failed_or_empty"] == ["osm"]
    with open(out / "sites.csv") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["name"] == "Queen FHT" and rows[0]["sources"] == "ontario_moh; overture"
    assert os.path.getsize(out / "excluded.csv") > 0
    assert "Open Government Licence" in (out / "ATTRIBUTION.txt").read_text()
    assert json.loads((out / "summary.json").read_text())["sites_after_dedupe"] == 1


def test_missing_fsa_is_estimated_from_nearest_record():
    with_postal = rec(sid="a", name="Some Dental", postal="M6H 1A1", lat=43.6600, lon=-79.4300)
    no_postal = rec(source="osm", sid="b", name="Duke Medical Clinic", postal="", lat=43.6630, lon=-79.4310)
    far_away = rec(source="osm", sid="c", name="Remote Clinic", postal="", lat=44.5, lon=-80.0)
    assert build.guess_missing_fsas([with_postal, no_postal, far_away]) == 1
    assert no_postal.fsa == "M6H" and far_away.fsa == ""
    assert build.in_scope(no_postal, ["M6"]) and not build.in_scope(far_away, ["M6"])
