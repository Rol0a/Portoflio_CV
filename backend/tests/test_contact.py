"""Contact-form relay tests.

This is the only endpoint on the site that accepts personal data and the only
one that causes an outbound side effect, so the tests focus on the ways that
combination gets abused: header injection to turn it into a mail relay, floods
aimed at the owner's inbox, and bots filling every field they find.

`send_contact_message` is patched throughout — no test opens an SMTP
connection or sends real mail. Addresses used are example.com, which RFC 2606
reserves for exactly this.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services import contact_service, rate_limit_service

VALID = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "message": "I would like to discuss an analytical engine.",
}


@pytest.fixture(autouse=True)
def _isolate_rate_limiter():
    rate_limit_service.reset()
    yield
    rate_limit_service.reset()


@pytest.fixture(autouse=True)
def _configured():
    """Pretend the relay is configured, without needing real credentials."""
    with (
        patch.object(settings, "contact_to_email", "owner@example.com"),
        patch.object(settings, "smtp_host", "smtp.example.com"),
        patch.object(settings, "smtp_username", "relay@example.com"),
    ):
        yield


async def _post(payload: dict, peer: str = "198.51.100.5"):
    transport = ASGITransport(app=app, client=(peer, 0))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/contact", json=payload)


async def test_a_valid_message_is_relayed():
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()) as send:
        response = await _post(VALID)

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    send.assert_awaited_once()
    assert send.await_args.args == (VALID["name"], VALID["email"], VALID["message"])


async def test_nothing_is_persisted():
    """The design promise: contact data is relayed, never stored. If a future
    change adds a table, the privacy bench's schema assertions fail too.
    """
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()):
        await _post(VALID)

    from sqlalchemy import text

    from app.database import async_session_factory

    async with async_session_factory() as db:
        tables = {
            row[0]
            for row in await db.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
    assert not any("contact" in name or "message" in name for name in tables), (
        f"a contact/message table exists: {tables}"
    )


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({**VALID, "email": "not-an-address"}, "malformed email"),
        ({**VALID, "email": ""}, "empty email"),
        ({**VALID, "name": ""}, "empty name"),
        ({**VALID, "name": "   "}, "whitespace-only name"),
        ({**VALID, "message": ""}, "empty message"),
        ({**VALID, "message": "x" * 5001}, "oversized message"),
        ({**VALID, "name": "x" * 101}, "oversized name"),
        ({"name": "Ada"}, "missing fields"),
    ],
)
async def test_invalid_submissions_are_rejected(payload, reason):
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()) as send:
        response = await _post(payload)

    assert response.status_code == 422, reason
    send.assert_not_awaited()


@pytest.mark.parametrize(
    "hostile_name",
    [
        "Ada\r\nBcc: victim@example.com",
        "Ada\nBcc: victim@example.com",
        "Ada\rSubject: spam",
    ],
)
async def test_header_injection_is_refused(hostile_name):
    """A line break in a header field lets a submitter append headers of their
    own — Bcc above all — which would turn this form into an open relay
    sending from the owner's authenticated mailbox.
    """
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()) as send:
        response = await _post({**VALID, "name": hostile_name})

    assert response.status_code == 422
    send.assert_not_awaited()


async def test_the_message_builder_itself_rejects_injection():
    """Defence in depth: the schema rejects it first, but the mail layer must
    not rely on having been called through the route.
    """
    with pytest.raises(ValueError):
        contact_service._build_message("Ada\r\nBcc: victim@example.com", "ada@example.com", "hi")

    with pytest.raises(ValueError):
        contact_service._build_message("Ada", "ada@example.com\r\nBcc: victim@example.com", "hi")


async def test_visitor_never_controls_the_destination():
    """The To: address comes from configuration only. A submitter cannot aim
    the form at a third party, which is what makes it not a spam relay.
    """
    with patch.object(settings, "contact_to_email", "owner@example.com"):
        mail = contact_service._build_message("Ada", "ada@example.com", "hello")

    assert mail["To"] == "owner@example.com"
    # Reply-To carries the visitor so the owner can answer; From stays the
    # authenticated mailbox, or the mail fails SPF/DKIM.
    assert mail["Reply-To"] == "ada@example.com"
    assert mail["From"] != "ada@example.com"


async def test_honeypot_submissions_are_silently_dropped():
    """A bot filling the hidden field gets a response identical to success, so
    it has no signal to adapt — but nothing is sent.
    """
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()) as send:
        response = await _post({**VALID, "website": "http://spam.example.com"})

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    send.assert_not_awaited()


async def test_a_flood_from_one_address_is_rate_limited():
    """Unauthenticated and it sends mail, so without this it is a way to bury
    the owner's inbox.
    """
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()) as send:
        first = await _post(VALID)
        second = await _post(VALID)

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers
    assert send.await_count == 1


async def test_rate_limiting_is_per_address_not_global():
    """Keyed on IP — so one sender cannot lock everyone else out, the failure
    mode the proxy-header fix exists to prevent (see test_proxy_headers.py).
    """
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()):
        first = await _post(VALID, peer="198.51.100.5")
        other = await _post(VALID, peer="203.0.113.9")

    assert first.status_code == 200
    assert other.status_code == 200


async def test_delivery_failure_is_reported_not_swallowed():
    """The bug this whole feature replaces: the old form called
    preventDefault() and discarded the message while the visitor believed it
    had been sent. A failure must be visible.
    """
    failing = AsyncMock(side_effect=contact_service.ContactDeliveryError("smtp down"))
    with patch.object(contact_service, "send_contact_message", new=failing):
        response = await _post(VALID)

    assert response.status_code == 502
    assert "email directly" in response.json()["detail"]


async def test_form_reports_itself_unavailable_when_not_configured():
    with patch.object(settings, "contact_to_email", ""):
        response = await _post(VALID)

    assert response.status_code == 503


async def test_owner_address_is_never_echoed_back_to_the_client():
    """The destination is private. It must not leak through a response body,
    including error responses.
    """
    with patch.object(contact_service, "send_contact_message", new=AsyncMock()):
        ok = await _post(VALID)
    failing = AsyncMock(side_effect=contact_service.ContactDeliveryError("x"))
    with patch.object(contact_service, "send_contact_message", new=failing):
        failed = await _post(VALID, peer="203.0.113.44")

    for response in (ok, failed):
        assert "owner@example.com" not in response.text
