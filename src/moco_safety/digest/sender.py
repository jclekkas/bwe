from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import env, require_env


def send(subject: str, html: str, text: str) -> None:
    host = env("SMTP_HOST", "smtp.gmail.com")
    port = int(env("SMTP_PORT", "587") or "587")
    user = require_env("SMTP_USER")
    password = require_env("SMTP_PASS")
    to = require_env("DIGEST_TO")
    sender = env("DIGEST_FROM", user) or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
