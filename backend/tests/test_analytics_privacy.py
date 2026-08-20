"""Analytics test bench: the numbers are real, and no personal data is kept.

`architecture.md` §9 makes five promises about this subsystem — first-party
only, no PII, aggregate-first, bot-resistant, GDPR/CCPA-friendly by design.
Those are exactly the kind of claims that quietly stop being true: nothing
breaks when an extra field starts being stored, and a dashboard that silently
double-counts looks healthier than one that doesn't.

This file is split accordingly.

**Part 1 — the analytics are real.** Every figure the admin dashboard shows is
derived from events that genuinely happened: seeded counts must match reported
counts exactly, and the mechanisms that *reduce* counts (bot filtering,
deduplication, rate limiting) must actually drop the rows they claim to.

**Part 2 — no personal data.** The raw client IP and user agent must never
reach the database in any recoverable form, the daily-rotating salt must
actually rotate, and no column outside the documented set may appear.

All input here is synthetic: RFC 5737 documentation IP ranges and invented
identifiers. No real visitor data, and nothing personal, is needed to run it.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select, text

from app.database import async_session_factory, engine
from app.models.analytics import AnalyticsEvent, AnalyticsEventType
from app.schemas.analytics import AnalyticsEventCreate, Granularity
from app.services import analytics_service

# RFC 5737 reserved-for-documentation addresses — never routable, never a real
# person's IP.
VISITOR_IP = "198.51.100.23"
OTHER_VISITOR_IP = "203.0.113.77"

REAL_BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

MARKER = f"privacy-test-{uuid.uuid4()}"


def _session(suffix: str) -> str:
    """A distinct synthetic session id, namespaced so cleanup can find it."""
    return f"{MARKER}-{suffix}"


@pytest.fixture
async def db():
    async with async_session_factory() as session:
        yield session
        await session.execute(
            delete(AnalyticsEvent).where(AnalyticsEvent.session_id.like(f"{MARKER}%"))
        )
        await session.commit()


async def _record(db, session_id: str, event_type=AnalyticsEventType.page_view, **kwargs) -> str:
    payload = AnalyticsEventCreate(
        event_type=event_type,
        session_id=session_id,
        metadata=kwargs.pop("metadata", None),
        **kwargs,
    )
    return await analytics_service.record_event(
        db, payload, kwargs.pop("client_ip", VISITOR_IP), kwargs.pop("user_agent", REAL_BROWSER_UA)
    )


async def _rows(db, session_id: str) -> list[AnalyticsEvent]:
    result = await db.execute(
        select(AnalyticsEvent).where(AnalyticsEvent.session_id == session_id)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# Part 1 — the analytics are real
# --------------------------------------------------------------------------


async def test_a_recorded_event_is_actually_persisted(db):
    """The floor everything else rests on: a reported event exists as a row."""
    session_id = _session("persisted")

    assert await _record(db, session_id) == "recorded"

    rows = await _rows(db, session_id)
    assert len(rows) == 1
    assert rows[0].event_type == AnalyticsEventType.page_view


async def test_dashboard_totals_match_the_events_that_happened(db):
    """The core "are these numbers real" assertion: seed a known mix of events
    and require the dashboard's own aggregation to report exactly that mix —
    no inflation, no invented figures, no double counting.
    """
    before = await analytics_service.get_admin_analytics(db, days=1, granularity=Granularity.day)

    # Distinct sessions, because page_view dedup is per session+path.
    await _record(db, _session("agg-a"), AnalyticsEventType.page_view)
    await _record(db, _session("agg-b"), AnalyticsEventType.page_view)
    await _record(db, _session("agg-c"), AnalyticsEventType.github_click)

    after = await analytics_service.get_admin_analytics(db, days=1, granularity=Granularity.day)

    assert after.summary.total_page_views == before.summary.total_page_views + 2
    assert after.summary.github_clicks == before.summary.github_clicks + 1
    # The two page_view sessions are new, so unique sessions rises by exactly 2.
    assert after.summary.unique_sessions == before.summary.unique_sessions + 2


async def test_bot_traffic_is_dropped_not_counted(db):
    """§9 principle 4. A crawler hitting every page would otherwise dominate
    the numbers — the dashboard would be reporting robots as an audience.
    """
    session_id = _session("bot")

    status = await analytics_service.record_event(
        db,
        AnalyticsEventCreate(event_type=AnalyticsEventType.page_view, session_id=session_id),
        VISITOR_IP,
        BOT_UA,
    )

    assert status == "ignored"
    assert await _rows(db, session_id) == []


async def test_sessionless_events_are_dropped(db):
    """§9: "ignore events with no session_id" — without one there is nothing to
    deduplicate or rate-limit against, so such an event is unattributable.
    """
    status = await analytics_service.record_event(
        db,
        AnalyticsEventCreate(event_type=AnalyticsEventType.page_view, session_id=""),
        VISITOR_IP,
        REAL_BROWSER_UA,
    )
    assert status == "ignored"


async def test_repeated_page_view_of_the_same_path_counts_once(db):
    """§9's 30-second dedup window. Back-navigation and remounts would
    otherwise inflate page views for a visitor who never left.
    """
    session_id = _session("dedup")
    metadata = {"path": "/projects"}

    assert await _record(db, session_id, metadata=metadata) == "recorded"
    assert await _record(db, session_id, metadata=metadata) == "ignored"

    assert len(await _rows(db, session_id)) == 1


async def test_a_different_path_in_the_same_session_still_counts(db):
    """Dedup must not be so eager that real navigation disappears."""
    session_id = _session("dedup-distinct")

    assert await _record(db, session_id, metadata={"path": "/about"}) == "recorded"
    assert await _record(db, session_id, metadata={"path": "/skills"}) == "recorded"

    assert len(await _rows(db, session_id)) == 2


async def test_event_flood_from_one_session_is_rate_limited(db):
    """§9: max 60 events per session per minute. Bounds how far one client can
    distort the figures — and how many rows it can write.
    """
    session_id = _session("flood")
    limit = analytics_service.EVENT_RATE_LIMIT_MAX

    for index in range(limit):
        assert await _record(db, session_id, metadata={"path": f"/p/{index}"}) == "recorded"

    assert await _record(db, session_id, metadata={"path": "/p/over"}) == "rate_limited"
    assert len(await _rows(db, session_id)) == limit


# --------------------------------------------------------------------------
# Part 2 — no personal data is collected or stored
# --------------------------------------------------------------------------


async def test_raw_ip_never_appears_anywhere_in_the_stored_row(db):
    """Not just "ip_hash is a hash" — the address must not survive in any
    column, including the free-form JSONB metadata.
    """
    session_id = _session("no-raw-ip")
    await _record(db, session_id, metadata={"path": "/contact"})

    row = (await _rows(db, session_id))[0]
    serialized = " ".join(
        str(getattr(row, column.key)) for column in inspect(AnalyticsEvent).mapper.column_attrs
    )

    assert VISITOR_IP not in serialized, "the raw client IP reached the database"


async def test_raw_user_agent_never_appears_anywhere_in_the_stored_row(db):
    """§9: "no full user agents". The UA string is a fingerprinting vector —
    it identifies OS, browser and version together.
    """
    session_id = _session("no-raw-ua")
    await _record(db, session_id)

    row = (await _rows(db, session_id))[0]
    serialized = " ".join(
        str(getattr(row, column.key)) for column in inspect(AnalyticsEvent).mapper.column_attrs
    )

    assert REAL_BROWSER_UA not in serialized
    for fragment in ("Mozilla", "Chrome", "Linux", "AppleWebKit"):
        assert fragment not in serialized, f"user-agent fragment {fragment!r} was stored"


async def test_stored_ip_hash_is_not_reversible_to_the_address(db):
    """A hash of an IP with no secret is trivially reversible — the entire
    IPv4 space is ~4 billion entries, minutes of brute force. This asserts the
    stored digest is *not* a plain hash of the address, i.e. that the salt is
    genuinely mixed in.
    """
    session_id = _session("hash-salted")
    await _record(db, session_id)
    row = (await _rows(db, session_id))[0]

    unsalted = hashlib.sha256(VISITOR_IP.encode()).hexdigest()
    assert row.ip_hash != unsalted, "ip_hash is an unsalted digest and can be brute-forced back"
    assert len(row.ip_hash) == 64


async def test_ip_hash_rotates_daily_so_visitors_cannot_be_tracked_across_days(db):
    """§9's daily salt is what keeps this pseudonymous rather than a permanent
    per-visitor identifier: the same address must hash differently tomorrow,
    so histories cannot be joined across days.
    """
    today = analytics_service.hash_ip_daily(VISITOR_IP)

    real_datetime = analytics_service.datetime

    class _Tomorrow(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(days=1)

    analytics_service.datetime = _Tomorrow
    try:
        tomorrow = analytics_service.hash_ip_daily(VISITOR_IP)
    finally:
        analytics_service.datetime = real_datetime

    assert today != tomorrow, "the same IP hashes identically across days — a stable tracker"


async def test_two_visitors_are_distinguishable_on_the_same_day(db):
    """The counterpart: the hash must still separate visitors within a day, or
    "approximate unique counting" is meaningless. This is the property the
    proxy-header fix exists to preserve (see test_proxy_headers.py).
    """
    assert analytics_service.hash_ip_daily(VISITOR_IP) != analytics_service.hash_ip_daily(
        OTHER_VISITOR_IP
    )


async def test_no_unexpected_columns_exist_on_the_events_table(db):
    """Enumerated from the live schema rather than hardcoded, so a future
    migration that adds an email, name, or raw-IP column fails here instead of
    silently widening what the site collects.
    """
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'analytics_events'"
        )
    )
    columns = {row[0] for row in result}

    documented = {
        "id",
        "event_type",
        "session_id",
        "project_id",
        "project_slug",
        "locale",
        "metadata",
        "user_agent_hash",
        "ip_hash",
        "created_at",
    }
    assert columns == documented, (
        "analytics_events schema drifted from architecture.md §9; "
        f"unexpected={columns - documented} missing={documented - columns}"
    )


# Columns whose names look personal but hold the site owner's own content, not
# anything collected from a visitor. Waived as explicit (table, column) pairs
# rather than by excluding whole tables, so the same name appearing on a *new*
# table still fails and gets a deliberate review.
NON_VISITOR_COLUMNS = {
    ("skills", "name"),  # skill names the owner authored: "Python", "KiCad"
    ("technologies", "name"),  # technology tags on the owner's projects
    ("admin_users", "username"),  # the owner's own login, not a visitor's
}

PII_SHAPED_COLUMN_NAMES = [
    "email",
    "name",
    "phone",
    "address",
    "ip_address",
    "ip",
    "user_agent",
    "referrer",
    "fingerprint",
    "full_name",
    "message",
]


@pytest.mark.parametrize("forbidden", PII_SHAPED_COLUMN_NAMES)
async def test_no_pii_shaped_column_names_anywhere_in_the_schema(db, forbidden):
    """Widened deliberately beyond analytics_events: §9's promise is that the
    *site* holds no visitor PII, so a contact-form table quietly appearing with
    email/message columns should trip this too — which is the exact shape the
    unwired form on the Contact page would take if someone finished it without
    revisiting the privacy stance.
    """
    result = await db.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = :forbidden"
        ),
        {"forbidden": forbidden},
    )
    found = [pair for pair in result if tuple(pair) not in NON_VISITOR_COLUMNS]

    assert not found, (
        f"a column named {forbidden!r} exists on a visitor-facing table: {found}. "
        "If this is owner-authored content rather than visitor data, add it to "
        "NON_VISITOR_COLUMNS with a justification."
    )


async def test_stored_row_carries_no_free_text_from_the_visitor(db):
    """metadata is JSONB and therefore accepts anything a caller passes. The
    frontend only ever sends a route path (hooks/useAnalytics.ts), and this
    asserts that what lands in the row is that and nothing else — no form
    fields, no query strings, no typed input.
    """
    session_id = _session("metadata-shape")
    await _record(db, session_id, metadata={"path": "/contact"})

    row = (await _rows(db, session_id))[0]
    assert set(row.event_metadata) <= {"path"}, (
        f"unexpected metadata keys recorded: {set(row.event_metadata) - {'path'}}"
    )
    assert "?" not in row.event_metadata["path"], "a query string was stored with the path"


async def test_analytics_writes_require_no_identifying_input(db):
    """The end-to-end privacy statement: a complete, countable event needs
    nothing but an event type and a client-generated random id. No cookie, no
    account, no email — nothing the visitor is ever asked to provide.
    """
    session_id = _session("minimal")

    status = await analytics_service.record_event(
        db,
        AnalyticsEventCreate(event_type=AnalyticsEventType.page_view, session_id=session_id),
        client_ip="unknown",
        user_agent=None,
    )

    assert status == "recorded"
    row = (await _rows(db, session_id))[0]
    assert row.user_agent_hash is None
    assert row.project_id is None
    assert row.event_metadata is None
