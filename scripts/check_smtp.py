"""Verify the contact-form SMTP credentials without going through the form.

    docker compose exec backend python -m scripts.check_smtp          # log in only
    docker compose exec backend python -m scripts.check_smtp --send   # also send one test message

By default this authenticates and disconnects — it proves the App Password
works without putting mail in anyone's inbox. `--send` delivers a single test
message to CONTACT_TO_EMAIL (the owner's own address), which is the end-to-end
check worth running once before launch.

Nothing here prints the password, and a failure reports the SMTP error class
rather than echoing credentials back to the terminal.
"""

import argparse
import asyncio
import smtplib
import sys

from app.config import settings
from app.services import contact_service


def _mask(value: str) -> str:
    """Enough to confirm the right value is loaded, not enough to reuse it."""
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _report_config() -> bool:
    print("contact relay configuration:")
    print(f"  CONTACT_TO_EMAIL  {settings.contact_to_email or '(empty)'}")
    print(f"  SMTP_HOST         {settings.smtp_host}:{settings.smtp_port}")
    print(f"  SMTP_USE_TLS      {settings.smtp_use_tls} ({'SMTPS' if settings.smtp_use_tls else 'STARTTLS'})")
    print(f"  SMTP_USERNAME     {settings.smtp_username or '(empty)'}")
    print(f"  SMTP_PASSWORD     {_mask(settings.smtp_password)} ({len(settings.smtp_password)} chars)")
    print()

    if not settings.contact_email_configured:
        print("NOT CONFIGURED — the contact form will return 503.")
        print("Set CONTACT_TO_EMAIL, SMTP_HOST and SMTP_USERNAME in .env.")
        return False

    if not settings.smtp_password:
        print("SMTP_PASSWORD is empty — the form will return 502 on every submission.")
        print("Generate a Gmail App Password at https://myaccount.google.com/apppasswords")
        print("(requires 2-Step Verification) and put the 16 characters in .env.")
        return False

    # Google displays the App Password as "abcd efgh ijkl mnop"; pasting it
    # with the spaces is the single most common way this fails.
    if " " in settings.smtp_password:
        print("SMTP_PASSWORD contains spaces. Gmail shows App Passwords in groups")
        print("of four for readability — store the 16 characters with no spaces.")
        return False

    if settings.smtp_host.endswith("gmail.com") and len(settings.smtp_password) != 16:
        print(f"WARNING: Gmail App Passwords are 16 characters; this one is "
              f"{len(settings.smtp_password)}. If login fails, that is probably why "
              f"(an account password will not work — Google blocks it).")

    return True


def _login_only() -> None:
    if settings.smtp_use_tls:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    try:
        if not settings.smtp_use_tls:
            server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
    finally:
        server.quit()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send",
        action="store_true",
        help="also deliver a test message to CONTACT_TO_EMAIL",
    )
    args = parser.parse_args()

    if not _report_config():
        return 1

    print(f"connecting to {settings.smtp_host}:{settings.smtp_port} …")
    try:
        await asyncio.to_thread(_login_only)
    except smtplib.SMTPAuthenticationError:
        print("\nAUTHENTICATION FAILED.")
        print("  - Use an App Password, not the account password.")
        print("  - 2-Step Verification must be enabled on the account.")
        print("  - SMTP_USERNAME must be the full address.")
        return 1
    except Exception as exc:
        print(f"\nCONNECTION FAILED: {type(exc).__name__}: {exc}")
        print("  - Port 465 needs SMTP_USE_TLS=true; port 587 needs false.")
        print("  - Check the host can reach the SMTP server outbound.")
        return 1

    print("login OK — the App Password is valid.")

    if not args.send:
        print("\nRe-run with --send to deliver a test message end to end.")
        return 0

    print(f"sending a test message to {settings.contact_to_email} …")
    try:
        await contact_service.send_contact_message(
            "Contact form self-test",
            settings.contact_to_email,
            "This is an automated test from scripts/check_smtp.py.\n"
            "If it arrived, the portfolio contact form can deliver mail.\n"
            "Reply-To is set to the sender's address on a real submission.",
        )
    except contact_service.ContactDeliveryError as exc:
        print(f"\nDELIVERY FAILED: {exc}")
        return 1

    print("sent — check the inbox (and the spam folder the first time).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
