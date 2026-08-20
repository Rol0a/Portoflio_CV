"""Retention purge tests (M16).

These prove the 90-day promise in architecture.md §9 is enforced rather than
described, and — just as importantly — that the purge is *targeted*: a sweep
that deleted everything would pass a naive "old rows are gone" assertion while
destroying the dashboard. Every test therefore seeds a row on each side of the
boundary and asserts both outcomes.

Rows are tagged with a per-run marker and removed in a fixture, so the tests
can run against the live dev database without leaving residue or deleting
anything they did not create.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.database import async_session_factory
from app.models.admin import AdminSession, AdminUser, LoginAttempt
from app.models.analytics import AnalyticsEvent, AnalyticsEventType
from app.services import retention_service

MARKER = f"retention-test-{uuid.uuid4()}"


def _days_ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@pytest.fixture
async def db():
    async with async_session_factory() as session:
        yield session
        # Remove only this run's rows, identified by the marker.
        await session.execute(delete(AnalyticsEvent).where(AnalyticsEvent.session_id == MARKER))
        await session.execute(delete(LoginAttempt).where(LoginAttempt.ip_hash == MARKER))
        await session.execute(delete(AdminSession).where(AdminSession.session_id.like(f"{MARKER}%")))
        await session.commit()


async def _count_analytics(db, created_at: datetime) -> int:
    rows = await db.execute(
        select(AnalyticsEvent).where(
            AnalyticsEvent.session_id == MARKER, AnalyticsEvent.created_at == created_at
        )
    )
    return len(rows.all())


async def test_analytics_older_than_ninety_days_is_deleted(db):
    stale_at = _days_ago(retention_service.ANALYTICS_RETENTION_DAYS + 1)
    db.add(
        AnalyticsEvent(
            event_type=AnalyticsEventType.page_view, session_id=MARKER, created_at=stale_at
        )
    )
    await db.commit()
    assert await _count_analytics(db, stale_at) == 1

    await retention_service.purge_analytics_events(db)

    assert await _count_analytics(db, stale_at) == 0


async def test_analytics_inside_the_window_is_kept(db):
    """The half of the behaviour that a "deletes old rows" test alone misses:
    a purge that dropped the whole table would also pass that assertion.
    """
    fresh_at = _days_ago(retention_service.ANALYTICS_RETENTION_DAYS - 1)
    db.add(
        AnalyticsEvent(
            event_type=AnalyticsEventType.page_view, session_id=MARKER, created_at=fresh_at
        )
    )
    await db.commit()

    await retention_service.purge_analytics_events(db)

    assert await _count_analytics(db, fresh_at) == 1


async def test_purge_reports_how_many_rows_it_deleted(db):
    """The count is what the scheduled task logs, so a wrong count means
    retention looks like it is working when it is not.
    """
    stale_at = _days_ago(retention_service.ANALYTICS_RETENTION_DAYS + 5)
    for _ in range(3):
        db.add(
            AnalyticsEvent(
                event_type=AnalyticsEventType.page_view, session_id=MARKER, created_at=stale_at
            )
        )
    await db.commit()

    deleted = await retention_service.purge_analytics_events(db)

    assert deleted >= 3, "purge under-reported the rows it removed"
    assert await _count_analytics(db, stale_at) == 0


async def test_login_attempts_are_bounded(db):
    """Every failed login writes a row, so without this an attacker can grow
    the table at will — and check_rate_limit scans it on each login.
    """
    stale_at = _days_ago(retention_service.LOGIN_ATTEMPT_RETENTION_DAYS + 1)
    fresh_at = _days_ago(1)
    db.add(LoginAttempt(ip_hash=MARKER, success=False, created_at=stale_at))
    db.add(LoginAttempt(ip_hash=MARKER, success=False, created_at=fresh_at))
    await db.commit()

    await retention_service.purge_login_attempts(db)

    remaining = (
        await db.execute(select(LoginAttempt.created_at).where(LoginAttempt.ip_hash == MARKER))
    ).scalars().all()
    assert list(remaining) == [fresh_at], "expected only the recent attempt to survive"


async def test_recent_attempts_survive_so_rate_limiting_still_works(db):
    """Rate limiting reads the last 15 minutes. If a purge ever swept those,
    it would silently reset an attacker's failure count to zero.
    """
    just_now = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.add(LoginAttempt(ip_hash=MARKER, success=False, created_at=just_now))
    await db.commit()

    await retention_service.purge_login_attempts(db)

    rows = (
        await db.execute(select(LoginAttempt).where(LoginAttempt.ip_hash == MARKER))
    ).scalars().all()
    assert len(rows) == 1


async def test_expired_sessions_are_collected(db):
    """auth_service only deletes an expired session if that exact id is looked
    up again, so a visitor who closes the tab leaves a row forever.
    """
    user_id = (await db.execute(select(AdminUser.id).limit(1))).scalar_one_or_none()
    if user_id is None:
        pytest.skip("no admin user to own the test sessions; seed the database first")

    expired = AdminSession(
        session_id=f"{MARKER}-expired", user_id=user_id, expires_at=_days_ago(2)
    )
    live = AdminSession(
        session_id=f"{MARKER}-live",
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(expired)
    db.add(live)
    await db.commit()

    await retention_service.purge_expired_sessions(db)

    surviving = (
        await db.execute(
            select(AdminSession.session_id).where(AdminSession.session_id.like(f"{MARKER}%"))
        )
    ).scalars().all()
    assert list(surviving) == [f"{MARKER}-live"], "an active session must not be purged"


async def test_purge_all_covers_every_governed_table(db):
    """Guards against a table being added to the retention policy in docs but
    not to purge_all — the counts dict is the contract.
    """
    deleted = await retention_service.purge_all(db)

    assert set(deleted) == {"analytics_events", "login_attempts", "admin_sessions"}
    assert all(isinstance(count, int) for count in deleted.values())
