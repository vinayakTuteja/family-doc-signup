# Ontario family practice site list

`clinics/` builds one deduplicated list of family practice sites in Ontario from every free,
open source we can use. Outreach goes to sites (clinic locations), so the list is of sites,
with individual physicians merged into the site they practise at when the data shows it.

## Sources

| Source | What it adds | Licence | Notes |
| --- | --- | --- | --- |
| Ontario Ministry of Health Service Provider Locations | Family Health Teams, Community Health Centres, Indigenous primary care, nurse practitioner-led clinics, nursing stations | Open Government Licence – Ontario | About 600 sites; team-based care only |
| Overture Maps places | Family practices, doctors' offices, walk-ins, with phone, email and website where known | CDLA-Permissive-2.0, Apache-2.0 or CC0 (per record) | About 4,500 Ontario records before cleaning; newest release used automatically |
| OpenStreetMap (Overpass API) | Extra doctors and clinics mapped by volunteers | ODbL 1.0 | Internal use is fine; publishing a database built from it requires ODbL |

Not automated on purpose:

- **CPSO physician register.** No bulk download, and its terms grant no licence to its content.
  Use it by hand to verify sites in pilot areas. Ask CPSO in writing before any bulk use.
- **Google Places.** Its terms forbid storing results, so it cannot feed this list.

Every site keeps its sources, source record IDs and licences, and `ATTRIBUTION.txt` is written
with each build.

## What the build does

1. **Load** every source.
2. **Normalize** postal codes, phone numbers (toll-free numbers dropped as shared call
   centres), emails, websites (directory and social sites ignored) and street addresses.
3. **Classify** each record: drop dentists, labs, imaging, pharmacies, spas, therapists,
   specialists and similar. Clinics that clearly say they are a family practice are kept even
   if they also have a pharmacy or lab on site. Kept records are labelled `family_practice`,
   `walk_in`, `team_based` or `np_led`, with `high`, `medium` or `low` confidence.
4. **Deduplicate** (rules in `clinics/dedupe.py`):
   - same email or phone within 2 km, or in the same urban FSA
   - same website within 300 m, with similar names or the same street address
   - very similar names (92+ out of 100) in the same area
   - similar names (80+) at the same street address or within 60 m

   "Same area" means within 300 m, or the same urban FSA and within 1.5 km. Rural FSAs (second
   character 0) can cover tens of kilometres, so sharing one is never enough by itself.
   Records at different street addresses more than 150 m apart are never merged. If they share
   contact details they are linked under one `org_id`, which is how chains show up.
5. **Review list.** Near misses go to `review_pairs.csv` for a person to mark `same` or
   `different`. Feeding that file back in with `--decisions` applies the decisions on every
   later build.

Names are compared without generic words (clinic, medical, centre, family, dr...) and
regardless of word order, so "Klassen R A Dr" matches "Dr. R.A. Klassen".

## Running it

```bash
pip install -r requirements-pipeline.txt
python -m clinics.build                       # all sources, all of Ontario
python -m clinics.build --fsa M4 M5 M6        # just some postal areas
python -m clinics.build --decisions data/clinics/review_pairs.csv
```

Output goes to `data/clinics/`, which is not committed to git.

On GitHub, the **build clinic list** workflow (Actions tab → Run workflow) runs all three
sources, including OpenStreetMap, and attaches the results to the run as a download. It also
runs on the 3rd of every month, after Overture's monthly release.

## Output columns (`sites.csv`)

| Column | Meaning |
| --- | --- |
| `site_id` | Stable ID, derived from the highest-priority source record in the site |
| `name`, `other_names` | Preferred name (Ministry first, then Overture, then OpenStreetMap) and the rest |
| `practice_type`, `confidence` | Classification described above |
| `address`, `city`, `postal_code`, `fsa`, `lat`, `lon` | Location |
| `phones`, `emails`, `websites` | All contact details found across sources |
| `sources`, `source_ids`, `licences` | Where every part came from |
| `record_count`, `match_reasons` | How many records were merged, and why |
| `org_id` | Shared by separate sites that share contact details (chains, multi-site teams) |
| `needs_location_check` | No postal code and no address in any source |

## First run (Ontario Ministry of Health + Overture, November 2026)

About 5,150 records loaded. About 1,900 were dropped as not family practice. That left 3,251
records, which merged into **3,022 sites**: about 1,520 high confidence, 1,130 medium and 370
low. 137 sites were confirmed by both sources. About 2,390 sites have a phone and about 710 have
an email. OpenStreetMap is added when the GitHub workflow runs.

## Known limits

- Coverage of solo and small fee-for-service practices depends on Overture and OpenStreetMap,
  and is incomplete. CPSO checks in pilot areas show how much is missing.
- Specialists' offices that do not say their specialty in the name can slip through as
  `medium`. Start outreach with `high` and `medium`, and check `low` by hand.
- Several family physicians in one building can appear as separate sites. Many of these are
  flagged in the review list as "same building".
- An email or phone found here is not permission to email a clinic. Check each clinic's
  website for "do not email" wording before outreach (see [compliance.md](compliance.md)).
