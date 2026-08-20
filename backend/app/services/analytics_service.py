import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analytics import AnalyticsEvent, AnalyticsEventType
from app.models.project import Locale, Project, ProjectTranslation
from app.schemas.analytics import (
    AdminAnalyticsResponse,
    AnalyticsEventCreate,
    AnalyticsSummary,
    Granularity,
    RecentEventOut,
    TimeseriesPoint,
    TopProjectOut,
)

RECENT_EVENTS_LIMIT = 15
TOP_PROJECTS_LIMIT = 10

# architecture.md §9: "Ignore events from known bot user-agent strings"
BOT_USER_AGENT_PATTERN = re.compile(
    r"bot|crawler|spider|crawling|curl|wget|python-requests|python-httpx|"
    r"headlesschrome|phantomjs|scrapy|slurp|bingpreview|facebookexternalhit",
    re.IGNORECASE,
)

EVENT_RATE_LIMIT_WINDOW = timedelta(minutes=1)
EVENT_RATE_LIMIT_MAX = 60  # §7: "Max 60 events per session per minute"
PAGE_VIEW_DEDUP_WINDOW = timedelta(seconds=30)  # §9 duplicate-prevention table

# "Live visitor tracking" (M8 extension): a session counts as active if it has
# emitted ANY event in this window, not just a page_view. Page views alone
# would undercount a visitor who's sitting on one page interacting (a
# project-link click, a language change) without navigating — there's no
# heartbeat event type in this app, so "any recent event" is the closest
# available proxy for "someone is here right now". 5 minutes is short enough
# to read as "now" on an admin dashboard, long enough that a visitor reading
# a single page doesn't flicker in and out between events.
ACTIVE_VISITOR_WINDOW_MINUTES = 5


def is_bot_user_agent(user_agent: str | None) -> bool:
    return bool(user_agent) and BOT_USER_AGENT_PATTERN.search(user_agent) is not None


def hash_ip_daily(ip: str) -> str:
    """SHA-256 of IP + a salt that rotates daily (architecture.md §9): lets same-day
    events be grouped for approximate unique-visitor counting without the hash being
    stable (and thus trackable) across days.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{ip}:{day}:{settings.session_secret_key}".encode()).hexdigest()


def hash_user_agent(user_agent: str) -> str:
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


async def _event_count_in_window(db: AsyncSession, session_id: str, window: timedelta) -> int:
    since = datetime.now(timezone.utc) - window
    stmt = select(func.count()).select_from(AnalyticsEvent).where(
        AnalyticsEvent.session_id == session_id, AnalyticsEvent.created_at >= since
    )
    return (await db.execute(stmt)).scalar_one()


async def _is_duplicate_page_view(db: AsyncSession, session_id: str, path: str | None) -> bool:
    since = datetime.now(timezone.utc) - PAGE_VIEW_DEDUP_WINDOW
    stmt = (
        select(func.count())
        .select_from(AnalyticsEvent)
        .where(
            AnalyticsEvent.session_id == session_id,
            AnalyticsEvent.event_type == AnalyticsEventType.page_view,
            AnalyticsEvent.created_at >= since,
            AnalyticsEvent.event_metadata["path"].astext == path,
        )
    )
    return (await db.execute(stmt)).scalar_one() > 0


async def record_event(
    db: AsyncSession,
    payload: AnalyticsEventCreate,
    client_ip: str,
    user_agent: str | None,
) -> str:
    """Validates, filters, and persists one analytics event. Returns a status
    string ("recorded", "ignored", or "rate_limited") — the route always answers
    200 with this status rather than erroring, since a tracking beacon has no
    useful way to react to a 4xx.
    """
    if not payload.session_id or is_bot_user_agent(user_agent):
        return "ignored"

    if await _event_count_in_window(db, payload.session_id, EVENT_RATE_LIMIT_WINDOW) >= EVENT_RATE_LIMIT_MAX:
        return "rate_limited"

    path = payload.metadata.get("path") if payload.metadata else None
    if payload.event_type == AnalyticsEventType.page_view and await _is_duplicate_page_view(
        db, payload.session_id, path
    ):
        return "ignored"

    project_id = None
    if payload.project_slug:
        project_id = (
            await db.execute(select(Project.id).where(Project.slug == payload.project_slug))
        ).scalar_one_or_none()

    db.add(
        AnalyticsEvent(
            event_type=payload.event_type,
            session_id=payload.session_id,
            project_id=project_id,
            project_slug=payload.project_slug,
            locale=payload.locale,
            event_metadata=payload.metadata,
            user_agent_hash=hash_user_agent(user_agent) if user_agent else None,
            ip_hash=hash_ip_daily(client_ip),
        )
    )
    await db.commit()
    return "recorded"


async def _count(db: AsyncSession, event_type: AnalyticsEventType, since: datetime) -> int:
    stmt = select(func.count()).select_from(AnalyticsEvent).where(
        AnalyticsEvent.event_type == event_type, AnalyticsEvent.created_at >= since
    )
    return (await db.execute(stmt)).scalar_one()


async def get_active_visitor_count(db: AsyncSession) -> int:
    """Distinct sessions with at least one event in the last
    `ACTIVE_VISITOR_WINDOW_MINUTES` — the number the Network Health admin
    page shows as "active now" (M8 extension, merged with the standalone
    `noc` service's data at the route layer in routes/admin.py, keeping this
    service's only data source `analytics_events`, same as every other
    function here).

    No new storage, no new transport: this is a query over the table M8
    already built, computed fresh on every request rather than sampled on a
    timer, which is what makes it "live" rather than "as of the last NOC
    poll".
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=ACTIVE_VISITOR_WINDOW_MINUTES)
    stmt = select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
        AnalyticsEvent.created_at >= since
    )
    return (await db.execute(stmt)).scalar_one()


async def get_admin_analytics(db: AsyncSession, days: int, granularity: Granularity) -> AdminAnalyticsResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_page_views = await _count(db, AnalyticsEventType.page_view, since)
    total_project_views = await _count(db, AnalyticsEventType.project_view, since)
    github_clicks = await _count(db, AnalyticsEventType.github_click, since)
    cv_downloads = await _count(db, AnalyticsEventType.cv_download, since)
    contact_clicks = await _count(db, AnalyticsEventType.contact_click, since)

    unique_sessions = (
        await db.execute(
            select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
                AnalyticsEvent.event_type == AnalyticsEventType.page_view,
                AnalyticsEvent.created_at >= since,
            )
        )
    ).scalar_one()

    language_rows = await db.execute(
        select(AnalyticsEvent.locale, func.count(func.distinct(AnalyticsEvent.session_id)))
        .where(AnalyticsEvent.event_type == AnalyticsEventType.page_view, AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.locale)
    )
    language_distribution = {locale.value: count for locale, count in language_rows if locale is not None}

    bucket = func.date_trunc(granularity.value, AnalyticsEvent.created_at)
    timeseries_rows = await db.execute(
        select(
            bucket.label("bucket"),
            func.count().filter(AnalyticsEvent.event_type == AnalyticsEventType.page_view),
            func.count(func.distinct(AnalyticsEvent.session_id)).filter(
                AnalyticsEvent.event_type == AnalyticsEventType.page_view
            ),
        )
        .where(AnalyticsEvent.created_at >= since)
        .group_by(bucket)
        .order_by(bucket)
    )
    timeseries = [
        TimeseriesPoint(date=row_bucket.date().isoformat(), page_views=page_views, unique_sessions=sessions)
        for row_bucket, page_views, sessions in timeseries_rows
    ]

    top_projects_rows = await db.execute(
        select(
            AnalyticsEvent.project_slug,
            func.coalesce(ProjectTranslation.title, AnalyticsEvent.project_slug),
            func.count(),
        )
        .outerjoin(Project, Project.slug == AnalyticsEvent.project_slug)
        .outerjoin(
            ProjectTranslation,
            (ProjectTranslation.project_id == Project.id) & (ProjectTranslation.locale == Locale.en),
        )
        .where(AnalyticsEvent.event_type == AnalyticsEventType.project_view, AnalyticsEvent.created_at >= since)
        .where(AnalyticsEvent.project_slug.is_not(None))
        .group_by(AnalyticsEvent.project_slug, ProjectTranslation.title)
        .order_by(func.count().desc())
        .limit(TOP_PROJECTS_LIMIT)
    )
    top_projects = [
        TopProjectOut(slug=slug, title=title, views=views) for slug, title, views in top_projects_rows
    ]

    recent_rows = await db.execute(
        select(AnalyticsEvent.event_type, AnalyticsEvent.project_slug, AnalyticsEvent.created_at)
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(RECENT_EVENTS_LIMIT)
    )
    recent_events = [
        RecentEventOut(event_type=event_type.value, project_slug=project_slug, timestamp=created_at.isoformat())
        for event_type, project_slug, created_at in recent_rows
    ]

    return AdminAnalyticsResponse(
        summary=AnalyticsSummary(
            total_page_views=total_page_views,
            unique_sessions=unique_sessions,
            total_project_views=total_project_views,
            github_clicks=github_clicks,
            cv_downloads=cv_downloads,
            contact_clicks=contact_clicks,
            language_distribution=language_distribution,
        ),
        timeseries=timeseries,
        top_projects=top_projects,
        recent_events=recent_events,
    )
