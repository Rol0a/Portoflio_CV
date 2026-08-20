"""Relay contact-form submissions to the site owner's inbox.

**Nothing is stored.** The message is composed, handed to the SMTP server, and
dropped. `architecture.md` §16 originally leaned toward "form-to-database (no
email service dependency)"; relaying instead keeps the promise in §9 that the
database holds no visitor PII — a `contact_submissions` table with name, email
and message columns would be the largest concentration of personal data on the
site, would need its own retention policy, and would sit in every backup.

The trade-off, stated plainly: if SMTP fails there is no second copy, so the
route must report the failure to the visitor rather than swallowing it. Losing
a message silently is what the unwired form did before this existed.

The destination address is read from configuration and never leaves the server
— it is not in the frontend bundle, the API responses, or the repository.
Publishing it would hand it to every scraper that loads the page.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


class ContactDeliveryError(RuntimeError):
    """Raised when the message could not be handed to the SMTP server."""


def _reject_header_injection(value: str, field: str) -> None:
    """Refuse newlines in anything destined for a mail header.

    `name` and `email` are attacked this way: a `\\r\\n` in either lets a
    submitter append headers of their own — `Bcc:` above all — turning the
    form into a relay that mails arbitrary third parties from the owner's
    address. `EmailMessage` guards against this itself, but a request that
    tries it is hostile and should be refused outright rather than sanitised
    and delivered.
    """
    if any(char in value for char in "\r\n"):
        raise ValueError(f"{field} contains a line break")


def _build_message(name: str, email: str, message: str) -> EmailMessage:
    _reject_header_injection(name, "name")
    _reject_header_injection(email, "email")

    mail = EmailMessage()
    # From is the authenticated mailbox, never the visitor: sending as them
    # would fail SPF/DKIM and land the mail in spam, if it were accepted at all.
    mail["From"] = settings.smtp_from or settings.smtp_username
    mail["To"] = settings.contact_to_email
    mail["Subject"] = f"Portfolio contact — {name}"
    # Reply-To is how the owner answers: hitting reply goes to the visitor.
    mail["Reply-To"] = email
    mail.set_content(
        f"From: {name} <{email}>\n"
        f"Sent via the portfolio contact form.\n"
        f"\n"
        f"{message}\n"
    )
    return mail


def _send_sync(mail: EmailMessage) -> None:
    if settings.smtp_use_tls:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    try:
        if not settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(mail)
    finally:
        server.quit()


async def send_contact_message(name: str, email: str, message: str) -> None:
    """Deliver one submission. Raises ContactDeliveryError if it cannot."""
    if not settings.contact_email_configured:
        raise ContactDeliveryError("contact email is not configured")

    mail = _build_message(name, email, message)
    try:
        # smtplib is blocking; keep it off the event loop.
        await asyncio.to_thread(_send_sync, mail)
    except ValueError:
        raise
    except Exception as exc:
        # Never log the message body or the sender's address — this is the one
        # place real visitor PII passes through, and logs outlive the request.
        logger.error("contact delivery failed: %s", type(exc).__name__)
        raise ContactDeliveryError("could not deliver the message") from exc

    logger.info("contact message relayed")
