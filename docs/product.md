# Product overview

## The problem

About 1.9 million people in Ontario want a family doctor and do not have one (Government of
Ontario, Budget 2026). Health Care Connect, the provincial matching service, reached only about
11% of them, and only about 7% of eligible physicians took patients from it (Auditor General of
Ontario, 2025). Real capacity exists outside that system but is hard to find. Patients find it by
checking websites, calling clinics and filling in waitlist forms by hand.

## The service

Patients sign up once. We contact family practices within the distance they choose, ask whether
they are taking new patients, and tell patients when a practice has room. Patients apply to the
practice directly. The service is free, and nobody can pay to get ahead.

## Phase 1 (built): patient signup

- One question per screen, about 3 minutes, works on older phones and without JavaScript.
- Questions: email, phone (optional), postal code, travel distance (1 to 25 km slider), who
  needs a doctor, household size, whether a household would split, age group, language, time
  without a doctor, health card status, Health Care Connect status, optional need and access
  questions (with separate consent), how they heard about us, consent.
- Email confirmation before anyone is on the list.
- A manage link in every email: still looking, found a doctor, or delete everything.
- Daily retention job (see [compliance.md](compliance.md)).
- Admin dashboard with counts only, small numbers hidden, and a CSV export by area.

## Phase 2 (next): clinic outreach

- Build the clinic list for pilot Toronto neighbourhoods by hand (clinic websites, CPSO register).
- One combined email per clinic, never one per patient: "N people within your area are looking."
- Buttons in the email: Accepting (number of spots), No capacity now, Pause, Unsubscribe.
  Every button opens a confirm page so email security scanners cannot click them.
- "No capacity" means we ask again in about 3 months. Any request to stop is permanent.
- Skip clinics whose websites say not to email them about new patients.

## Phase 3: matching

- When a practice reports N spots, offer them to the top N eligible patients by priority score
  (see [ranking.md](ranking.md)), within each patient's distance.
- Households that said they would split can be offered part of a practice's spots.
- Each offer is held for 5 business days, with a reminder on day 3, then released to the next person.
- Patients contact the practice themselves. We never send patient names or details to clinics.

## Data model

| Table | What it holds |
| --- | --- |
| `contacts` | Email, optional phone, hashed tokens for email links |
| `profiles` | Postal code, distance, answers, need flags (with consent), status and dates; linked to a contact by random ID |
| `consent_log` | Which consent wording version each person agreed to, and which scopes |
| `monthly_counts` | Signups per month by postal prefix, kept after individual records are deleted |

Profile status moves through `pending` (email not confirmed) → `active` → `connected` or
`deidentified`.
