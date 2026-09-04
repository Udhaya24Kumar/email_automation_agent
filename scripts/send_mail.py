import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Required environment variables (both send_email() and
# send_email_with_attachment() below use these):
#   GMAIL_USER          - the Gmail address sending the email
#   GMAIL_APP_PASSWORD  - a 16-character App Password (NOT your normal
#                          Gmail password — generate one at
#                          https://myaccount.google.com/apppasswords,
#                          which requires 2-Step Verification to be on)
#   TO_EMAIL             - recipient address (defaults to GMAIL_USER,
#                          i.e. emailing yourself)


def _build_message(
    subject: str,
    html_body: str,
    gmail_user: str,
    to_email: str,
    attachment_path=None,
    attachment_name: str | None = None,
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_email

    body = MIMEMultipart("alternative")
    body.attach(MIMEText("Please view this email in an HTML-capable client.", "plain"))
    body.attach(MIMEText(html_body, "html"))
    msg.attach(body)

    if attachment_path:
        attachment_path = Path(attachment_path)
        name = attachment_name or attachment_path.name
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=name)
        part["Content-Disposition"] = f'attachment; filename="{name}"'
        msg.attach(part)

    return msg


def _send(msg: MIMEMultipart, gmail_user: str, gmail_app_password: str, to_email: str) -> None:
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, [to_email], msg.as_string())


def send_email(subject: str, html_body: str) -> None:
    """Send an HTML email via Gmail SMTP using an App Password.

    Required environment variables:
      GMAIL_USER          - the Gmail address sending the email
      GMAIL_APP_PASSWORD  - a 16-character App Password (NOT your normal
                             Gmail password — generate one at
                             https://myaccount.google.com/apppasswords,
                             which requires 2-Step Verification to be on)
      TO_EMAIL             - recipient address (defaults to GMAIL_USER,
                             i.e. emailing yourself)
    """
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email = os.environ.get("TO_EMAIL", gmail_user)

    msg = _build_message(subject, html_body, gmail_user, to_email)
    _send(msg, gmail_user, gmail_app_password, to_email)


def send_email_with_attachment(
    subject: str,
    html_body: str,
    attachment_path,
    attachment_name: str | None = None,
) -> None:
    """Same as send_email(), but attaches a file (e.g. the weekly PDF
    report). Uses the same Gmail SMTP + App Password env vars as
    send_email() — see its docstring.
    """
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    to_email = os.environ.get("TO_EMAIL", gmail_user)

    msg = _build_message(
        subject, html_body, gmail_user, to_email, attachment_path, attachment_name
    )
    _send(msg, gmail_user, gmail_app_password, to_email)
