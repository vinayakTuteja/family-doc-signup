"""Find records that describe the same practice site and merge them.

"Same area" means within 300 m, or in the same urban FSA and within 1.5 km. Rural FSAs (second
character 0, e.g. P0V) can span tens of kilometres, so sharing one is never enough on its own.

Two records are the same site when any of these hold:

1. They share an email address or phone number and are within 2 km (or share an urban FSA).
2. They share a website, are within 300 m, and have similar names or the same street address.
3. Their names are very similar (92+ out of 100) and they are in the same area.
4. Their names are fairly similar (80+) and they share a street address or are within 60 m.

Records at different street addresses more than 150 m apart are never merged. If they share a
phone, email or website (chains often do), they are linked into the same "organization"
instead, so outreach can treat them as one group of separate sites.

Names are compared after removing generic words (clinic, medical, centre, family, dr...), with
word order ignored, so "Klassen R A Dr" matches "Dr. R.A. Klassen".

Pairs that come close but do not meet a rule go to a review list for a person to decide.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from . import normalize as n
from .record import SourceRecord

SOURCE_PRIORITY = {"ontario_moh": 0, "overture": 1, "osm": 2}
TYPE_PRIORITY = {"team_based": 0, "np_led": 1, "family_practice": 2, "walk_in": 3}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}

GRID = 0.004  # degrees, about 350 to 450 m in Ontario


@dataclass
class Item:
    idx: int
    rec: SourceRecord
    practice_type: str
    confidence: str
    name_key: str = ""
    street: str = ""
    phones: set = field(default_factory=set)
    emails: set = field(default_factory=set)
    webs: set = field(default_factory=set)

    @classmethod
    def build(cls, idx, rec, practice_type, confidence):
        return cls(
            idx=idx, rec=rec, practice_type=practice_type, confidence=confidence,
            name_key=n.name_key(rec.name),
            street=n.street_key(rec.address),
            phones=set(rec.phones),
            emails=set(rec.emails),
            webs={k for k in (n.website_key(w) for w in rec.websites) if k},
        )

    def cell(self):
        if self.rec.lat is None or self.rec.lon is None:
            return None
        return (int(self.rec.lat // GRID), int(self.rec.lon // GRID))


class UnionFind:
    def __init__(self, size):
        self.parent = list(range(size))

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def name_similarity(a: Item, b: Item) -> float:
    if a.name_key and b.name_key:
        score = fuzz.token_sort_ratio(a.name_key, b.name_key)
        # A one-word key ("barrie", "toronto") is mostly a place name: weak evidence.
        if min(len(a.name_key.split()), len(b.name_key.split())) == 1 and a.name_key != b.name_key:
            score *= 0.85
        return score
    # A name made only of generic words ("Medical Clinic"): compare full names, more strictly.
    return fuzz.ratio((a.rec.name or "").lower(), (b.rec.name or "").lower()) * 0.85


def is_rural_fsa(fsa: str) -> bool:
    return len(fsa) >= 2 and fsa[1] == "0"


def compare(a: Item, b: Item) -> tuple[str, str] | None:
    """Return ("merge" | "org" | "review", reason) or None."""
    dist = n.distance_m(a.rec.lat, a.rec.lon, b.rec.lat, b.rec.lon)
    same_urban_fsa = bool(a.rec.fsa) and a.rec.fsa == b.rec.fsa and not is_rural_fsa(a.rec.fsa)
    same_area = dist <= 300 or (same_urban_fsa and (dist <= 1500 or dist == float("inf")))
    same_street = bool(a.street) and a.street == b.street
    different_sites = bool(a.street) and bool(b.street) and a.street != b.street and dist > 150

    shared = (a.emails & b.emails) | (a.phones & b.phones) | (a.webs & b.webs)
    if different_sites:
        if shared:
            return "org", "shares contact details with another site"
        return None

    sim = name_similarity(a, b)
    contact_close = dist <= 2000 or same_urban_fsa
    if a.emails & b.emails and contact_close:
        return "merge", f"same email ({sorted(a.emails & b.emails)[0]})"
    if a.phones & b.phones and contact_close:
        return "merge", f"same phone ({sorted(a.phones & b.phones)[0]})"
    if a.webs & b.webs and dist <= 300 and (sim >= 60 or same_street):
        return "merge", f"same website ({sorted(a.webs & b.webs)[0]})"
    if sim >= 92 and same_area:
        return "merge", f"very similar name ({sim:.0f}) in the same area"
    if sim >= 80 and (same_street or dist <= 60):
        return "merge", f"similar name ({sim:.0f}) at the same address"
    if sim >= 75 and same_area:
        return "review", f"similar name ({sim:.0f}) in the same area"
    if (same_street or dist <= 40) and sim >= 50:
        return "review", f"same building, names partly similar ({sim:.0f})"
    return None


def candidate_pairs(items: list[Item]):
    """Pairs worth comparing: same FSA, nearby grid cells, or any shared contact detail."""
    pairs = set()
    by_fsa, by_cell, by_contact = defaultdict(list), defaultdict(list), defaultdict(list)
    for it in items:
        if it.rec.fsa:
            by_fsa[it.rec.fsa].append(it.idx)
        c = it.cell()
        if c:
            by_cell[c].append(it.idx)
        for key in it.emails | {"tel:" + p for p in it.phones} | {"web:" + w for w in it.webs}:
            by_contact[key].append(it.idx)

    def add_group(idxs):
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = idxs[i], idxs[j]
                pairs.add((a, b) if a < b else (b, a))

    for group in by_fsa.values():
        add_group(group)
    for group in by_contact.values():
        add_group(group)
    for (x, y), group in by_cell.items():
        neighbours = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbours.extend(by_cell.get((x + dx, y + dy), []))
        for a in group:
            for b in neighbours:
                if a != b:
                    pairs.add((a, b) if a < b else (b, a))
    return pairs


def stable_id(members: list[Item]) -> str:
    anchor = min(members, key=lambda m: (SOURCE_PRIORITY[m.rec.source], m.rec.source_id))
    digest = hashlib.sha1(f"{anchor.rec.source}:{anchor.rec.source_id}".encode()).hexdigest()[:12]
    return f"site_{digest}"


def merge_cluster(members: list[Item], reasons: list[str]) -> dict:
    members = sorted(members, key=lambda m: (SOURCE_PRIORITY[m.rec.source], -CONFIDENCE_RANK[m.confidence]))
    best = members[0]
    with_postal = next((m for m in members if m.rec.postal_code), best)
    with_address = next((m for m in members if m.rec.address), with_postal)

    def union_ordered(values):
        seen, out = set(), []
        for v in values:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return out

    practice_type = min((m.practice_type for m in members), key=lambda t: TYPE_PRIORITY[t])
    confidence = max((m.confidence for m in members), key=lambda c: CONFIDENCE_RANK[c])
    return {
        "site_id": stable_id(members),
        "name": best.rec.name,
        "other_names": "; ".join(union_ordered(m.rec.name for m in members[1:] if m.rec.name != best.rec.name)),
        "practice_type": practice_type,
        "confidence": confidence,
        "address": with_address.rec.address,
        "city": with_address.rec.city or with_postal.rec.city,
        "postal_code": with_postal.rec.postal_code,
        "fsa": with_postal.rec.fsa,
        "lat": round(best.rec.lat, 6) if best.rec.lat is not None else "",
        "lon": round(best.rec.lon, 6) if best.rec.lon is not None else "",
        "phones": "; ".join(union_ordered(p for m in members for p in m.rec.phones)),
        "emails": "; ".join(union_ordered(e for m in members for e in m.rec.emails)),
        "websites": "; ".join(union_ordered(w for m in members for w in m.rec.websites)),
        "sources": "; ".join(union_ordered(m.rec.source for m in members)),
        "source_ids": "; ".join(f"{m.rec.source}:{m.rec.source_id}" for m in members),
        "licences": "; ".join(union_ordered(m.rec.licence for m in members)),
        "needs_location_check": "yes" if not with_postal.rec.postal_code and not with_address.rec.address else "",
        "record_count": len(members),
        "match_reasons": "; ".join(union_ordered(reasons)),
    }


def record_key(rec: SourceRecord) -> str:
    return f"{rec.source}:{rec.source_id}"


def deduplicate(classified: list[tuple[SourceRecord, str, str]], decisions: dict | None = None):
    """classified: (record, practice_type, confidence).

    decisions: {(record_key_a, record_key_b): "same" | "different"} from a reviewed review list.
    Returns (sites, review_pairs).
    """
    decisions = decisions or {}
    items = [Item.build(i, rec, t, c) for i, (rec, t, c) in enumerate(classified)]
    key_to_idx = {record_key(it.rec): it.idx for it in items}
    sites_uf, org_uf = UnionFind(len(items)), UnionFind(len(items))
    reasons = defaultdict(list)
    review = []

    def decided(a, b):
        ka, kb = record_key(items[a].rec), record_key(items[b].rec)
        return decisions.get((ka, kb)) or decisions.get((kb, ka))

    for (ka, kb), verdict in decisions.items():
        if verdict == "same" and ka in key_to_idx and kb in key_to_idx:
            sites_uf.union(key_to_idx[ka], key_to_idx[kb])
            reasons[key_to_idx[ka]].append("confirmed by a reviewer")
            reasons[key_to_idx[kb]].append("confirmed by a reviewer")

    for a, b in sorted(candidate_pairs(items)):
        verdict = decided(a, b)
        if verdict == "different":
            continue
        result = compare(items[a], items[b])
        if not result:
            continue
        kind, why = result
        if kind == "merge":
            sites_uf.union(a, b)
            reasons[a].append(why)
            reasons[b].append(why)
        elif kind == "org":
            org_uf.union(a, b)
        else:
            review.append((a, b, why))

    clusters = defaultdict(list)
    for it in items:
        clusters[sites_uf.find(it.idx)].append(it)

    sites, site_of = [], {}
    for root, members in clusters.items():
        site = merge_cluster(members, [r for m in members for r in reasons[m.idx]])
        sites.append(site)
        for m in members:
            site_of[m.idx] = site["site_id"]

    # Organization groups: sites linked by shared contact details across separate addresses.
    org_members = defaultdict(set)
    for it in items:
        org_members[org_uf.find(it.idx)].add(site_of[it.idx])
    org_of_site = {}
    for group in org_members.values():
        if len(group) > 1:
            org_id = "org_" + hashlib.sha1(";".join(sorted(group)).encode()).hexdigest()[:10]
            for sid in group:
                org_of_site[sid] = org_id
    for s in sites:
        s["org_id"] = org_of_site.get(s["site_id"], "")

    review_rows = []
    seen = set()
    for a, b, why in review:
        sa, sb = site_of[a], site_of[b]
        if sa == sb or (sa, sb) in seen:
            continue
        seen.add((sa, sb))
        ra, rb = items[a].rec, items[b].rec
        review_rows.append({
            "record_a": record_key(ra), "record_b": record_key(rb),
            "site_id_a": sa, "name_a": ra.name, "address_a": ra.address, "source_a": ra.source,
            "site_id_b": sb, "name_b": rb.name, "address_b": rb.address, "source_b": rb.source,
            "fsa": ra.fsa or rb.fsa,
            "distance_m": round(n.distance_m(ra.lat, ra.lon, rb.lat, rb.lon)),
            "reason": why,
            "decision": "",  # fill in: same | different
        })

    sites.sort(key=lambda s: (s["fsa"] or "ZZZ", s["name"].lower()))
    return sites, review_rows
