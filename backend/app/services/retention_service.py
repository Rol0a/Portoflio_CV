"""Data retention — the one place that enforces how long anything is kept.

`architecture.md` §9 promises "raw events older than 90 days are archived or
deleted" and lists "aggregate-first — raw data is ephemeral" as a design
principle. Until this module existed, nothing implemented either: three tables
grew without bound, so the 90-day figure was documentation rather than
behaviour. That makes it a broken *privacy* commitment, not just a disk
problem — the site keeps per-visitor rows it promised to discard.

Why one module rather than three ad-hoc cleanups (M16): the windows are policy,
and policy split across call sites drifts. `network_health_samples` already
demonstrates the failure mode — its 7-day window is declared twice, in
`noc/monitor.py` and `network_health_service.py`, and nothing keeps the two in
step. Everything here is a named constant with the reason for its value.

Each function returns the number of rows it deleted so the caller can log real
figures instead of asserting success blindly.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminSession, LoginAttempt
from app.models.analytics import AnalyticsEvent

logger = logging.getLogger(__name__)

# architecture.md §9: "First implementation: delete raw events > 90 days via
# scheduled script." This is that policy, now enforced rather than described.
ANALYTICS_RETENTION_DAYS = 90

# Rate limiting (auth_service.check_rate_limit) only ever looks back 15
# minutes, so anything older is kept purely for security review, not for
# function. 30 days is enough to investigate a brute-force attempt while
# bounding a table that an attacker can otherwise grow at will — every failed
# login writes a row, so unbounded retention makes sustained guessing a slow
# disk-fill attack as well.
LOGIN_ATTEMPT_RETENTION_DAYS = 30

# Expired sessions are dead weight the moment they lapse: get_session_user
# rejects them on sight. The grace period exists only so a session that expires
# mid-request isn't deleted out from under an in-flight lookup.
EXPIRED_SESSION_GRACE = timedelta(hours=1)


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def purge_analytics_events(db: AsyncSession) -> int:
    """Delete raw analytics events past the retention window.

    Aggregates already shown on the dashboard are computed on demand from
    these rows, so purging shortens the window the dashboard can report on.
    That is the intended trade — §9 chose ephemeral raw data over indefinite
    per-visitor history.
    """
    result = await db.execute(
        delete(AnalyticsEvent).where(AnalyticsEvent.created_at < _cutoff(ANALYTICS_RETENTION_DAYS))
    )
    await db.commit()
    return result.rowcount or 0


async def purge_login_attempts(db: AsyncSession) -> int:
    result = await db.execute(
        delete(LoginAttempt).where(LoginAttempt.created_at < _cutoff(LOGIN_ATTEMPT_RETENTION_DAYS))
    )
    await db.commit()
    return result.rowcount or 0


async def purge_expired_sessions(db: AsyncSession) -> int:
    """Delete sessions that have already expired.

    `auth_service.get_session_user` deletes an expired session only when that
    exact session id is looked up again — so a session that expires and is
    never revisited (the normal case: the visitor simply closes the tab) stays
    in the table permanently. This is the sweep that actually collects them.
    """
    result = await db.execute(
        delete(AdminSession).where(AdminSession.expires_at < datetime.now(timezone.utc) - EXPIRED_SESSION_GRACE)
    )
    await db.commit()
    return result.rowcount or 0


async def purge_all(db: AsyncSession) -> dict[str, int]:
    """Run every retention sweep. Returns per-table deletion counts."""
    deleted = {
        "analytics_events": await purge_analytics_events(db),
        "login_attempts": await purge_login_attempts(db),
        "admin_sessions": await purge_expired_sessions(db),
    }
    total = sum(deleted.values())
    if total:
        logger.info("retention purge deleted %d rows: %s", total, deleted)
    else:
        logger.debug("retention purge: nothing past retention")
    return deleted


async def oldest_row_ages(db: AsyncSession) -> dict[str, float | None]:
    """Age in days of the oldest row in each governed table, or None if empty.

    Exists so retention can be *observed* rather than assumed — a purge task
    that silently stops running looks identical to one with nothing to do, and
    this is what tells the two apart.
    """
    ages: dict[str, float | None] = {}
    for name, column in (
        ("analytics_events", AnalyticsEvent.created_at),
        ("login_attempts", LoginAttempt.created_at),
        ("admin_sessions", AdminSession.created_at),
    ):
        oldest = (await db.execute(select(func.min(column)))).scalar_one_or_none()
        ages[name] = None if oldest is None else (datetime.now(timezone.utc) - oldest).total_seconds() / 86400
    return ages
