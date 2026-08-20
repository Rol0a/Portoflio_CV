"""Tests for the "live visitor tracking" M8 extension.

This is deliberately not a new subsystem: it's one query
(`analytics_service.get_active_visitor_count`) over the table M8 already
built, merged with the standalone `noc` service's data at the route layer
(`routes/admin.py`'s `get_network_health`) rather than a new service, new
storage, or a push transport. These tests cover the query's correctness —
the window boundary, distinct-session counting, and that a session counts
as active from ANY event type, not just page_view — and that the merge into
`/api/v1/admin/network-health` actually happens.

Reuses the RFC 5737 synthetic-data pattern from test_analytics_privacy.py:
no real visitor data is needed to exercise this.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database import async_session_factory
from app.main import app
from app.models.analytics import AnalyticsEvent, AnalyticsEventType
from app.models.admin import AdminSession, AdminUser
from app.services import analytics_service, auth_service

MARKER = f"active-visitors-test-{uuid.uuid4()}"


def _session(suffix: str) -> str:
    return f"{MARKER}-{suffix}"


@pytest.fixture
async def db():
    async with async_session_factory() as session:
        yield session
        await session.execute(delete(AnalyticsEvent).where(AnalyticsEvent.session_id.like(f"{MARKER}%")))
        await session.commit()


async def _seed_event(db, session_id: str, minutes_ago: float, event_type=AnalyticsEventType.page_view) -> None:
    db.add(
        AnalyticsEvent(
            event_type=event_type,
            session_id=session_id,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
    )
    await db.commit()


# --------------------------------------------------------------------------
# analytics_service.get_active_visitor_count
# --------------------------------------------------------------------------


async def test_a_session_active_seconds_ago_counts(db):
    await _seed_event(db, _session("just-now"), minutes_ago=0.1)
    before = await analytics_service.get_active_visitor_count(db)

    await _seed_event(db, _session("just-now-2"), minutes_ago=0.1)
    after = await analytics_service.get_active_visitor_count(db)

    assert after == before + 1


async def test_a_session_outside_the_window_does_not_count(db):
    stale_minutes = analytics_service.ACTIVE_VISITOR_WINDOW_MINUTES + 5
    before = await analytics_service.get_active_visitor_count(db)

    await _seed_event(db, _session("stale"), minutes_ago=stale_minutes)
    after = await analytics_service.get_active_visitor_count(db)

    assert after == before, "an event outside the active window was counted"


async def test_the_same_session_with_multiple_recent_events_counts_once(db):
    session_id = _session("multi-event")
    before = await analytics_service.get_active_visitor_count(db)

    await _seed_event(db, session_id, minutes_ago=0.1, event_type=AnalyticsEventType.page_view)
    await _seed_event(db, session_id, minutes_ago=0.2, event_type=AnalyticsEventType.github_click)
    await _seed_event(db, session_id, minutes_ago=0.3, event_type=AnalyticsEventType.contact_click)
    after = await analytics_service.get_active_visitor_count(db)

    assert after == before + 1, "one session with three recent events counted as more than one visitor"


async def test_a_non_page_view_event_alone_still_counts_as_active(db):
    """The whole reason this isn't `unique_sessions`' page_view-only query:
    a visitor interacting with the current page (a click, a language change)
    without navigating is still "here", and should still count.
    """
    before = await analytics_service.get_active_visitor_count(db)

    await _seed_event(db, _session("click-only"), minutes_ago=0.1, event_type=AnalyticsEventType.language_change)
    after = await analytics_service.get_active_visitor_count(db)

    assert after == before + 1


async def test_two_distinct_recent_sessions_count_as_two(db):
    before = await analytics_service.get_active_visitor_count(db)

    await _seed_event(db, _session("visitor-a"), minutes_ago=0.1)
    await _seed_event(db, _session("visitor-b"), minutes_ago=0.1)
    after = await analytics_service.get_active_visitor_count(db)

    assert after == before + 2


# --------------------------------------------------------------------------
# GET /api/v1/admin/network-health — the merge
# --------------------------------------------------------------------------


@pytest.fixture
async def admin_cookie(db):
    """A real, logged-in admin session cookie, the same way test_noc_role.py
    and the auth tests authenticate — the endpoint under test requires it.
    """
    username = f"active-visitors-admin-{uuid.uuid4().hex[:8]}"
    password = "test-password-not-a-real-secret"
    user = AdminUser(username=username, password_hash=auth_service.hash_password(password))
    db.add(user)
    await db.flush()
    session_id, _ = await auth_service.create_session(db, user)
    yield session_id
    await db.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
    await db.execute(delete(AdminUser).where(AdminUser.id == user.id))
    await db.commit()


async def test_network_health_endpoint_includes_active_visitors(db, admin_cookie):
    await _seed_event(db, _session("endpoint-check"), minutes_ago=0.1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/network-health",
            cookies={"portfolio_session": admin_cookie},
        )

    assert response.status_code == 200
    body = response.json()
    assert "active_visitors" in body, "the network-health response has no active_visitors field"
    assert body["active_visitors"]["count"] >= 1
    assert body["active_visitors"]["window_minutes"] == analytics_service.ACTIVE_VISITOR_WINDOW_MINUTES


async def test_network_health_endpoint_still_requires_admin_auth():
    """The merge must not have loosened the endpoint's protection — it's the
    same route, same dependency, just a richer response body."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/network-health")

    assert response.status_code == 401
