import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg.attach(MIMEText("Please view this email in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, [to_email], msg.as_string())