# Family doctor finder (working name: OpenPanel)

A free website that helps people in Ontario find a family doctor. Patients sign up once; we
contact family practices within the distance they choose and tell them when one has room.

**Status:** phase 1 (patient signup) is built and tested. Clinic outreach and matching are next.
See [docs/product.md](docs/product.md).

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/product.md](docs/product.md) | The problem, what is built, the phases ahead, data model |
| [docs/ranking.md](docs/ranking.md) | How we decide who hears about an opening first, and why |
| [docs/compliance.md](docs/compliance.md) | Privacy, anti-spam and CPSO notes, retention schedule, launch checklist |
| [docs/clinic-list.md](docs/clinic-list.md) | How the Ontario family practice site list is built from free sources |
| [CHANGELOG.md](CHANGELOG.md) | What changed and when |

## See it without installing anything

Open `preview/index.html` in any browser. It is a click-through simulation of the whole site
(signup, test inbox, confirmation, admin dashboard). Nothing is saved or sent. Rebuild it after
changing the signup page with `python preview/build.py`.

## Run it on your computer

You need Python 3.12 or newer (https://www.python.org/downloads/).

- **Mac:** open Terminal in this folder and run `./run_local.sh`
- **Windows:** double-click `run_local.bat`

Then open:

- http://localhost:8000 for the site
- http://localhost:8000/dev/outbox for a test inbox (emails are saved there, not sent)
- http://localhost:8000/admin for the dashboard (user `admin`, password `dev`)

Test data goes in `data/local.db`. Delete the `data` folder to start fresh.

## Run the tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests also run automatically on GitHub for every push and pull request.

## Build the clinic list

```bash
pip install -r requirements-pipeline.txt
python -m clinics.build --fsa M4 M5 M6     # or leave out --fsa for all of Ontario
```

Or run the **build clinic list** workflow from the GitHub Actions tab to get all sources,
including OpenStreetMap, as a download. Details in [docs/clinic-list.md](docs/clinic-list.md).

## Put it online (Fly.io, Toronto region)

1. Install the Fly CLI and sign up: https://fly.io/docs/flyctl/install/
2. Change `app = "family-doc-signup"` in `fly.toml` to a unique name.
3. Create the app and a storage volume in Toronto:
   ```bash
   fly launch --no-deploy --copy-config
   fly volumes create signup_data --region yyz --size 1
   ```
4. Set secrets (all settings are listed in `.env.example`):
   ```bash
   fly secrets set BASE_URL=https://your-domain.ca ADMIN_PASSWORD='long-random-password' \
     ORG_LEGAL_NAME='...' ORG_MAILING_ADDRESS='...' ORG_CONTACT_EMAIL='...' \
     EMAIL_BACKEND=smtp SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM='OpenPanel <hello@your-domain.ca>'
   ```
5. `fly deploy`

For email, use a transactional provider (for example Amazon SES in the Canada Central region,
Postmark or Mailgun) and set up SPF, DKIM and DMARC on your domain. Work through the launch
checklist in [docs/compliance.md](docs/compliance.md) before going live.

## Project layout

```
app/
  main.py          web routes: signup, confirm, manage, admin, test inbox
  questions.py     every question and option (form, validation and dashboard read from here)
  scoring.py       priority score for matching
  retention.py     daily data retention schedule
  emailer.py       email templates and sending
  db.py            database schema (SQLite)
  security.py      tokens and rate limiting
  config.py        settings from environment variables
  templates/       pages
  static/          style.css and app.js (step-by-step form, plain ES5 for older phones)
clinics/           builds the deduplicated Ontario family practice site list (see docs/clinic-list.md)
docs/              product, ranking, compliance and clinic list notes
preview/           click-through simulation and the script that builds it
scripts/           retention.py for running retention by hand
tests/             automated tests
run_local.sh/.bat  one-step local start
Dockerfile, fly.toml   deployment
```
