from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage

from ..config import env


def send(subject: str, html: str, text: str) -> bool:
    """Send the digest. Returns True if sent, False if SMTP isn't configured.

    Missing credentials are a soft failure so the workflow's fetch+commit
    still succeeds when the user hasn't added secrets yet.
    """
    user = env("SMTP_USER")
    password = env("SMTP_PASS")
    to = env("DIGEST_TO")
    if not (user and password and to):
        missing = [n for n, v in [("SMTP_USER", user), ("SMTP_PASS", password), ("DIGEST_TO", to)] if not v]
        print(f"[digest] skipping email — missing secrets: {', '.join(missing)}", file=sys.stderr)
        return False

    host = env("SMTP_HOST", "smtp.gmail.com")
    port = int(env("SMTP_PORT", "587") or "587")
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
    print(f"[digest] sent to {to}", file=sys.stderr)
    return True
