"""Email delivery via SMTP (Gmail app password)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import SMTPConfig

log = logging.getLogger(__name__)


def send_email(smtp: SMTPConfig, subject: str, html_body: str, text_body: str) -> None:
    if not smtp.email_to:
        raise RuntimeError("EMAIL_TO is empty — nothing to send")
    if not (smtp.user and smtp.app_password):
        raise RuntimeError("SMTP_USER / SMTP_APP_PASSWORD not set")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp.email_from
    msg["To"] = ", ".join(smtp.email_to)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(smtp.user, smtp.app_password)
        server.sendmail(smtp.email_from, smtp.email_to, msg.as_string())
    log.info("email sent to %s", ", ".join(smtp.email_to))
