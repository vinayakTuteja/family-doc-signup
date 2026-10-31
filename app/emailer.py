"""Email sending.

Every message is multipart (plain text + HTML) so it reads in any email app. Buttons are
plain links styled with inline CSS inside tables, which Outlook, Apple Mail, Gmail and
Yahoo all render. Links only open a page; any action needs a click on that page, so
corporate link scanners that open every URL cannot change anything by accident.
"""

import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from datetime import datetime, timezone

from .config import settings

log = logging.getLogger("emailer")


def _button(url: str, label: str) -> str:
    safe_url = html.escape(url, quote=True)
    safe_label = html.escape(label)
    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:16px 0;">
  <tr>
    <td bgcolor="#1f5f4a" style="border-radius:6px;">
      <a href="{safe_url}" target="_blank"
         style="display:inline-block;padding:12px 22px;font-family:Arial,Helvetica,sans-serif;
                font-size:16px;color:#ffffff;text-decoration:none;border-radius:6px;">{safe_label}</a>
    </td>
  </tr>
</table>"""


def _footer_text(manage_url: str) -> str:
    return (
        f"\n--\n{settings.org_legal_name}\n{settings.org_mailing_address}\n{settings.org_contact_email}\n"
        f"Change your details, stop emails or delete your data: {manage_url}\n"
        f"We are not affiliated with the Government of Ontario, Ontario Health or Health Care Connect.\n"
    )


def _footer_html(manage_url: str) -> str:
    return f"""
<p style="margin-top:32px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#666666;line-height:1.5;">
  {html.escape(settings.org_legal_name)}<br>
  {html.escape(settings.org_mailing_address)}<br>
  <a href="mailto:{html.escape(settings.org_contact_email)}" style="color:#666666;">{html.escape(settings.org_contact_email)}</a><br><br>
  <a href="{html.escape(manage_url, quote=True)}" style="color:#666666;">Change your details, stop emails or delete your data</a><br>
  We are not affiliated with the Government of Ontario, Ontario Health or Health Care Connect.
</p>"""


def _wrap_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#ffffff;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
<tr><td style="padding:24px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;">
<tr><td style="font-family:Arial,Helvetica,sans-serif;font-size:16px;color:#222222;line-height:1.5;">
{body}
</td></tr></table></td></tr></table></body></html>"""


def build_message(to: str, subject: str, text: str, html_body: str, manage_url: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Message-ID"] = make_msgid()
    msg["List-Unsubscribe"] = f"<{manage_url}>, <mailto:{settings.org_contact_email}?subject=unsubscribe>"
    msg.set_content(text + _footer_text(manage_url))
    msg.add_alternative(_wrap_html(html_body + _footer_html(manage_url)), subtype="html")
    return msg


def send(msg: EmailMessage) -> None:
    if settings.email_backend == "smtp":
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        log.info("Sent email to %s: %s", msg["To"], msg["Subject"])
        return

    # Console backend for development and tests: never sends, saves a copy instead.
    os.makedirs(settings.outbox_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = os.path.join(settings.outbox_dir, f"{stamp}.eml")
    with open(path, "wb") as f:
        f.write(bytes(msg))
    log.info("[console email] to=%s subject=%s saved=%s", msg["To"], msg["Subject"], path)


def verification_email(to: str, verify_url: str, manage_url: str) -> EmailMessage:
    name = settings.app_name
    text = (
        f"Thanks for signing up with {name}.\n\n"
        f"Please confirm your email so we can start looking for a family doctor near you:\n{verify_url}\n\n"
        "If you did not sign up, ignore this email and your details will be deleted within 7 days.\n\n"
        "While you wait, please also register with Health Care Connect, Ontario's free matching service: "
        "https://www.ontario.ca/page/find-family-doctor-or-nurse-practitioner\n"
    )
    body = f"""
<p>Thanks for signing up with {html.escape(name)}.</p>
<p>Please confirm your email so we can start looking for a family doctor near you.</p>
{_button(verify_url, "Confirm my email")}
<p style="font-size:14px;color:#444444;">If the button does not work, copy this link into your browser:<br>
<a href="{html.escape(verify_url, quote=True)}" style="color:#1f5f4a;word-break:break-all;">{html.escape(verify_url)}</a></p>
<p style="font-size:14px;color:#444444;">If you did not sign up, ignore this email and your details will be deleted within 7 days.</p>
<p style="font-size:14px;color:#444444;">While you wait, please also register with
<a href="https://www.ontario.ca/page/find-family-doctor-or-nurse-practitioner" style="color:#1f5f4a;">Health Care Connect</a>,
Ontario's free matching service.</p>"""
    return build_message(to, f"Confirm your email for {name}", text, body, manage_url)


def already_registered_email(to: str, manage_url: str) -> EmailMessage:
    name = settings.app_name
    text = (
        f"Someone tried to sign up for {name} with this email, which is already on our list.\n\n"
        f"If it was you, you can update your details here:\n{manage_url}\n\n"
        "If it was not you, you can ignore this email.\n"
    )
    body = f"""
<p>Someone tried to sign up for {html.escape(name)} with this email, which is already on our list.</p>
<p>If it was you, you can update your details or remove yourself here:</p>
{_button(manage_url, "Manage my signup")}
<p style="font-size:14px;color:#444444;">If it was not you, you can ignore this email.</p>"""
    return build_message(to, f"You are already signed up with {name}", text, body, manage_url)


def still_looking_email(to: str, manage_url: str) -> EmailMessage:
    name = settings.app_name
    text = (
        f"You signed up with {name} almost a year ago.\n\n"
        f"Are you still looking for a family doctor? If so, confirm here so we keep you on the list:\n{manage_url}\n\n"
        "If we do not hear from you within 30 days, we will delete your contact details.\n"
    )
    body = f"""
<p>You signed up with {html.escape(name)} almost a year ago.</p>
<p>Are you still looking for a family doctor? If so, tell us and we will keep you on the list.
If we do not hear from you within 30 days, we will delete your contact details.</p>
{_button(manage_url, "I am still looking")}"""
    return build_message(to, f"Are you still looking for a family doctor? ({name})", text, body, manage_url)
