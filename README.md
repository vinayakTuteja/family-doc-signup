# Family doctor signup (working name: OpenPanel)

Free signup site for people in Ontario who need a family doctor. It is phase 1 of a larger
service: we collect demand now, then contact nearby family practices and tell patients when
a practice has room.

## What it does today

- **Signup form.** Email (required), phone (optional), Ontario postal code, travel radius, who
  needs a doctor, age group, language, time without a doctor, health card status, Health Care
  Connect status, and optional yes/no need questions that need their own consent box.
- **Email confirmation.** Nobody is on the list until they click the link in the confirmation email.
- **Self-service link in every email.** People can confirm they are still looking, say they
  found a doctor, or delete all their data.
- **Data retention, run daily.** Unconfirmed signups are deleted after 7 days. Inactive people
  get a "still looking?" email at 11 months and are de-identified 30 days later. People who
  found a doctor are de-identified right away (or after 90 days if they agreed to a follow-up).
  De-identified records are deleted after 24 months. Monthly counts by area are kept.
- **Admin dashboard** at `/admin` (password protected): demand by postal prefix, age group,
  needs, language and referral source. Counts only, small numbers hidden. CSV export.
- **Priority score** (`app/scoring.py`) for later matching: capped need points, infants and
  75+, time without a doctor, plus a point per 30 days on the list. Not used yet; it exists so
  the rules are written down and tested.

## Privacy design

- Contact details sit in a separate table from location and answers, linked by a random ID.
- No names, no health card numbers, no diagnoses, no IP addresses stored.
- Need answers are kept only with separate consent.
- Email links carry random tokens; only hashes are stored.
- Links in emails open a page with a button. Nothing changes until the button is clicked, so
  clinic and corporate email scanners that open every link cannot trigger actions.
- Emails are plain text plus simple HTML, with table-based buttons that work in Outlook,
  Apple Mail, Gmail and Yahoo. Each email identifies the sender and includes the manage link
  and a `List-Unsubscribe` header.

## Run it on your computer

You need Python 3.12 or newer (https://www.python.org/downloads/).

- **Mac:** open Terminal in this folder and run `./run_local.sh`
- **Windows:** double-click `run_local.bat`

Then open:

- http://localhost:8000 for the site
- http://localhost:8000/dev/outbox for a test inbox (emails are saved there, not sent)
- http://localhost:8000/admin for the dashboard (user `admin`, password `dev`)

Test data is stored in `data/local.db`. Delete the `data` folder to start fresh.
Run the automated tests with `pip install -r requirements-dev.txt` and then `pytest -q`.

## Put it online (Fly.io, Toronto region)

1. Install the Fly CLI and sign up: https://fly.io/docs/flyctl/install/
2. Change `app = "family-doc-signup"` in `fly.toml` to a unique name.
3. Create the app and a volume in Toronto:
   ```bash
   fly launch --no-deploy --copy-config
   fly volumes create signup_data --region yyz --size 1
   ```
4. Set secrets (values from `.env.example`):
   ```bash
   fly secrets set BASE_URL=https://your-domain.ca ADMIN_PASSWORD='long-random-password' \
     ORG_LEGAL_NAME='...' ORG_MAILING_ADDRESS='...' ORG_CONTACT_EMAIL='...' \
     EMAIL_BACKEND=smtp SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM='OpenPanel <hello@your-domain.ca>'
   ```
5. `fly deploy`

Fly takes daily snapshots of volumes. Confirm the retention period in your Fly dashboard.

### Email provider

Use a transactional email provider (for example Amazon SES in the Canada Central region,
Postmark or Mailgun). Set up SPF, DKIM and DMARC records on your domain as the provider
instructs, or confirmation emails will land in spam.

## Before launch

- [ ] Have a lawyer review the privacy notice (`app/templates/privacy.html`) and the consent
      wording on the form. Bump `CONSENT_VERSION` whenever the wording changes.
- [ ] Set a real legal name, mailing address and privacy contact email (shown on every page and email).
- [ ] Choose a final name and domain; avoid anything that suggests a government service.
- [ ] Set a long, random `ADMIN_PASSWORD`.
- [ ] Set up the email provider with SPF, DKIM and DMARC, and send yourself test emails in
      Gmail, Outlook and Apple Mail.
- [ ] Decide who answers emails to the privacy contact, and how fast (access and correction requests).
- [ ] Write a short breach response plan (PIPEDA requires reporting breaches that pose a real
      risk of significant harm and keeping a record of every breach for 24 months).

## Project layout

```
app/
  main.py         routes: signup, confirm, manage, admin
  questions.py    every question and option (form, validation and dashboard read from here)
  scoring.py      priority score for future matching
  retention.py    daily retention schedule
  emailer.py      email templates and sending
  db.py           SQLite schema
  templates/      pages
  static/         stylesheet
scripts/retention.py   run retention manually
tests/                 pytest suite
```

## Next phases

1. Clinic list for pilot neighbourhoods and the clinic outreach email (one combined email per
   clinic, buttons for Accepting / Not now / Pause / Unsubscribe).
2. Matching: offer each opening to the top-ranked eligible patients, 5-business-day hold,
   reminder on day 3, then release to the next person.
3. Outcome follow-up and reporting for Ontario Health Teams.
