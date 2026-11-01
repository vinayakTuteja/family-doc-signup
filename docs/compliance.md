# Privacy and compliance notes

These notes record how the design maps to the rules we identified. They are not legal advice.
Have a health and privacy lawyer review them before launch.

## Privacy (PIPEDA)

The service is a private organization collecting data directly from patients, so the federal
privacy law (PIPEDA) applies. Ontario has no general private-sector privacy law. We are not a
PHIPA custodian; that changes if an Ontario Health Team later hires us to handle its patients'
health information.

| PIPEDA principle | How the design meets it |
| --- | --- |
| 4.2 Identifying purposes | Privacy notice lists every purpose, including measuring the service |
| 4.3 Consent | Required service consent; separate optional consent for need answers and for follow-up |
| 4.4 Limiting collection | No names, health card numbers, diagnoses, medications or IP addresses |
| 4.5 Limiting retention | Retention schedule below, run daily |
| 4.7 Safeguards | Contacts and answers in separate tables; hashed link tokens; Canadian hosting; admin shows counts only |
| 4.8 Openness | Plain-language privacy notice, published scoring rules |
| 4.9 Individual access | Manage link in every email; access and correction requests by email |
| s. 10.1 Breaches | Report breaches with a real risk of significant harm; keep a record of every breach for 24 months |

### Retention schedule

| Situation | What happens |
| --- | --- |
| Email not confirmed | Deleted after 7 days |
| On the list | "Still looking?" email after 11 months without activity; contact details deleted 30 days later if no answer |
| Found a doctor | Contact details deleted right away, or after 90 days if they agreed to a follow-up |
| After contact details are deleted | Postal prefix, age group, answers and dates kept up to 24 months, still protected as personal information |
| Totals | Monthly counts by area kept |

## Anti-spam law (CASL)

- Emails to patients: they asked for the service, which is express consent. Every email
  identifies the sender (legal name, mailing address, contact email) and has a manage and
  unsubscribe link plus a `List-Unsubscribe` header.
- Emails to clinics (phase 2): rely on the s. 6(5)(b) exemption for a message that "consists
  solely of an inquiry" about the clinic's business. Keep the email to the inquiry only: no
  marketing, no "join our platform". Ask for express consent (s. 10(1)) on the first reply.
- Unsubscribes (s. 11): honour any clear request to stop, however it is worded, within 10
  business days (we aim for same day). Opt-outs are global and permanent.

## CPSO policies

- Accepting New Patients (2025): physicians may prioritize high-need patients but may not
  refuse anyone only because of complex needs. Clinics are never offered a way to filter
  patients by health.
- Steering (O. Reg. 114/94 s. 7) and fee-splitting (O. Reg. 856/93): clinics never pay us, we
  never submit applications or send patient details to clinics, and patients apply directly.
  Confirm with CPSO's Physician Advisory Service before matching goes live. Check the regulation
  text on e-Laws.

## Ontario Human Rights Code

Priority for people 65 and over is permitted (s. 15). Age protection covers adults (s. 10), so
priority for infants is not an issue. Adults are never ranked lower for being older.

## Before launch

- [ ] Lawyer review of the privacy notice (`app/templates/privacy.html`), consent wording and
      clinic email. Bump `CONSENT_VERSION` whenever wording changes.
- [ ] Real legal name, mailing address and privacy contact email in the settings.
- [ ] Final name and domain that do not suggest a government service.
- [ ] Email provider with SPF, DKIM and DMARC; test in Gmail, Outlook and Apple Mail.
- [ ] Long random `ADMIN_PASSWORD`.
- [ ] Named person who answers privacy requests, and a target response time.
- [ ] Written breach response plan.
- [ ] CPSO Physician Advisory Service question on matching, before phase 3.
