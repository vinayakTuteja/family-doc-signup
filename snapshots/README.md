# Snapshots

Saved copies of generated data, so they are available after the GitHub workflow's downloads
expire (30 days). Regenerate with `python -m clinics.build` or the "build clinic list" workflow.

| Folder | What it is |
| --- | --- |
| `clinic-list-2026-11-09/` | Full Ontario run, all three sources: 4,325 sites (`sites.csv`), 139 pairs to review (`review_pairs.csv`), records dropped as not family practice (`excluded.csv`) |

This repository is private. These files include OpenStreetMap data (ODbL): if the repository
or these files are ever made public, the OpenStreetMap licence terms in `ATTRIBUTION.txt` apply.
