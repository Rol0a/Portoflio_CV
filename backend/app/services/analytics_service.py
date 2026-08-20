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
    DeviceCountOut,
    EngagementSummary,
    EventCountOut,
    Granularity,
    HourlyPointOut,
    RecentEventOut,
    ReferrerCountOut,
    TimeseriesPoint,
    TopPageOut,
    TopProjectOut,
)

RECENT_EVENTS_LIMIT = 15
TOP_PROJECTS_LIMIT = 10
TOP_PAGES_LIMIT = 10
TOP_REFERRERS_LIMIT = 10

# What a session with no referrer host is called in the breakdown. A visitor
# who typed the URL, used a bookmark, or came from a client that withholds the
# header is a real and interesting category — not missing data — so it gets a
# name rather than being dropped.
DIRECT_REFERRER = "direct"

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


# Coarse form factor, in the order they must be tested. Tablets first, because
# iPad Safari's UA contains "Mobile/15E148" and would otherwise classify as a
# phone; Android tablets are identified by the *absence* of the "Mobile" token
# that Android phones always carry, which is why that rule needs a lookahead
# rather than a keyword.
DEVICE_TABLET_PATTERN = re.compile(
    # The Android lookahead must scan the WHOLE remaining string, not just to
    # the end of the platform parenthesis: Chrome on an Android phone puts
    # "Mobile" *after* the closing paren
    # ("… (Linux; Android 14; Pixel 8) AppleWebKit/… Chrome/… Mobile Safari/…"),
    # so a `[^)]*` lookahead never sees it and files every phone as a tablet.
    r"ipad|tablet|kindle|silk|playbook|nexus (?:7|9|10)|android(?!.*mobile)",
    re.IGNORECASE,
)
DEVICE_MOBILE_PATTERN = re.compile(
    r"mobi|iphone|ipod|android|blackberry|bb10|windows phone|opera mini|iemobile",
    re.IGNORECASE,
)

DEVICE_MOBILE = "mobile"
DEVICE_TABLET = "tablet"
DEVICE_DESKTOP = "desktop"
# A request that carried no User-Agent header at all. Stored rather than left
# NULL on purpose: NULL is reserved to mean "written before this column
# existed", and the device/referrer breakdowns key on that distinction to
# report only the window they were actually collected over.
DEVICE_UNKNOWN = "unknown"


def is_bot_user_agent(user_agent: str | None) -> bool:
    return bool(user_agent) and BOT_USER_AGENT_PATTERN.search(user_agent) is not None


def classify_device(user_agent: str | None) -> str:
    """Reduce a User-Agent string to one of four coarse classes.

    This runs at write time and its *output* is what gets stored — the UA
    itself is only ever persisted as a truncated hash (`hash_user_agent`), and
    `docs/security.md` §9's "no full user agents" promise depends on it staying
    that way. Four buckets is deliberately less resolution than a UA parsing
    library would give: browser name and version would be a fingerprinting
    surface, and the question this answers is only "does the layout need to
    work on a phone", which four buckets answer completely.
    """
    if not user_agent:
        return DEVICE_UNKNOWN
    if DEVICE_TABLET_PATTERN.search(user_agent):
        return DEVICE_TABLET
    if DEVICE_MOBILE_PATTERN.search(user_agent):
        return DEVICE_MOBILE
    return DEVICE_DESKTOP


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

    # `ref` arrives through the metadata allowlist (that is what validates it as
    # a bare host), but it belongs in its own column: the referrer breakdown
    # groups on it, and a JSONB extraction can't use an index. Moved rather than
    # copied so there is exactly one place it lives.
    metadata = dict(payload.metadata) if payload.metadata else {}
    referrer_host = metadata.pop("ref", None)

    db.add(
        AnalyticsEvent(
            event_type=payload.event_type,
            session_id=payload.session_id,
            project_id=project_id,
            project_slug=payload.project_slug,
            locale=payload.locale,
            event_metadata=metadata or None,
            user_agent_hash=hash_user_agent(user_agent) if user_agent else None,
            ip_hash=hash_ip_daily(client_ip),
            device_class=classify_device(user_agent),
            referrer_host=referrer_host,
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


async def _get_engagement(db: AsyncSession, since: datetime) -> EngagementSummary:
    """Session-shaped metrics, all from one pass over the events in range.

    Everything here folds `analytics_events` down to one row per session first,
    then aggregates *those* rows — which is the only way these numbers come out
    right. Averaging over events instead would weight a visitor who read ten
    pages ten times as heavily as one who read a single page, and the whole
    point of a session metric is that each visit counts once.

    Note the denominator is every session with any event, not the
    `unique_sessions` figure in the summary above, which counts only sessions
    that emitted a page_view. The two differ by sessions whose page_view was
    suppressed as a 30-second duplicate while a click still landed.
    """
    session_stats = (
        select(
            AnalyticsEvent.session_id.label("session_id"),
            func.count().label("event_count"),
            func.count()
            .filter(AnalyticsEvent.event_type == AnalyticsEventType.page_view)
            .label("page_views"),
            func.min(AnalyticsEvent.created_at).label("first_seen"),
            func.max(AnalyticsEvent.created_at).label("last_seen"),
            func.count(func.distinct(func.date_trunc("day", AnalyticsEvent.created_at))).label("active_days"),
        )
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.session_id)
        .subquery()
    )

    total_sessions, bounced, avg_events, avg_pages, avg_duration, returning = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(
                    (session_stats.c.event_count == 1) & (session_stats.c.page_views == 1)
                ),
                func.coalesce(func.avg(session_stats.c.event_count), 0.0),
                func.coalesce(func.avg(session_stats.c.page_views), 0.0),
                func.coalesce(
                    func.avg(
                        func.extract("epoch", session_stats.c.last_seen - session_stats.c.first_seen)
                    ).filter(session_stats.c.event_count > 1),
                    0.0,
                ),
                func.count().filter(session_stats.c.active_days > 1),
            )
        )
    ).one()

    return EngagementSummary(
        bounce_rate=(bounced / total_sessions) if total_sessions else 0.0,
        pages_per_session=float(avg_pages),
        avg_events_per_session=float(avg_events),
        avg_session_duration_seconds=float(avg_duration),
        returning_sessions=returning,
    )


async def _get_top_pages(db: AsyncSession, since: datetime) -> list[TopPageOut]:
    """Which routes visitors actually open.

    `metadata.path` has been written on every page_view since the recording
    pipeline went in, and nothing has ever read it — the dashboard could say
    how many pages were viewed but not which ones. The allowlist in
    `schemas/analytics.py` guarantees the value is a bare route with query
    string and fragment already stripped, so grouping on it directly cannot
    fragment `/projects` across a dozen tracking-parameter variants.
    """
    path = AnalyticsEvent.event_metadata["path"].astext
    rows = await db.execute(
        select(path, func.count(), func.count(func.distinct(AnalyticsEvent.session_id)))
        .where(
            AnalyticsEvent.event_type == AnalyticsEventType.page_view,
            AnalyticsEvent.created_at >= since,
            path.is_not(None),
        )
        .group_by(path)
        .order_by(func.count().desc())
        .limit(TOP_PAGES_LIMIT)
    )
    return [TopPageOut(path=value, views=views, unique_sessions=sessions) for value, views, sessions in rows]


async def _get_event_breakdown(db: AsyncSession, since: datetime) -> list[EventCountOut]:
    """Every event type with its count, zero-filled.

    Zero-filling matters more than it looks: a type missing from the list is
    indistinguishable from a type that is never fired because its instrumentation
    broke. An explicit 0 says "we asked, and nobody did this".
    """
    rows = await db.execute(
        select(AnalyticsEvent.event_type, func.count())
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.event_type)
    )
    counts = {event_type: count for event_type, count in rows}
    return [
        EventCountOut(event_type=member.value, count=counts.get(member, 0))
        for member in AnalyticsEventType
    ]


def _session_dimensions_subquery(since: datetime):
    """One row per session carrying its device class and referrer host.

    Both dimensions are properties of a *visit*, not of each event: the
    referrer is only sent with a session's first page_view, so counting events
    would file every later event under "direct" and drown the real source. The
    `max()` picks the single non-null value each session has.

    `device_class IS NOT NULL` is the collection-window filter. Every row the
    instrumented build writes carries a class (down to the literal "unknown"
    for a request with no User-Agent), so this excludes exactly the rows that
    predate the column — which otherwise would be reported as an enormous
    "direct, unknown device" cohort that is really just "not measured".
    """
    return (
        select(
            AnalyticsEvent.session_id.label("session_id"),
            func.max(AnalyticsEvent.device_class).label("device_class"),
            func.max(AnalyticsEvent.referrer_host).label("referrer_host"),
        )
        .where(AnalyticsEvent.created_at >= since, AnalyticsEvent.device_class.is_not(None))
        .group_by(AnalyticsEvent.session_id)
        .subquery()
    )


async def _get_device_breakdown(db: AsyncSession, since: datetime) -> list[DeviceCountOut]:
    sessions = _session_dimensions_subquery(since)
    rows = await db.execute(
        select(sessions.c.device_class, func.count())
        .group_by(sessions.c.device_class)
        .order_by(func.count().desc())
    )
    return [DeviceCountOut(device_class=device, sessions=count) for device, count in rows]


async def _get_referrers(db: AsyncSession, since: datetime) -> list[ReferrerCountOut]:
    sessions = _session_dimensions_subquery(since)
    host = func.coalesce(sessions.c.referrer_host, DIRECT_REFERRER)
    rows = await db.execute(
        select(host, func.count()).group_by(host).order_by(func.count().desc()).limit(TOP_REFERRERS_LIMIT)
    )
    return [ReferrerCountOut(host=value, sessions=count) for value, count in rows]


async def _get_hourly_activity(db: AsyncSession, since: datetime) -> list[HourlyPointOut]:
    """Events per hour-of-day (UTC), all 24 buckets present.

    Answers the question a raw daily total cannot: *when* the site is read.
    All 24 are returned whether or not they have data, because a gap in the
    middle of a bar chart should be a visible zero rather than a missing bar
    that silently rescales the axis.
    """
    hour = func.extract("hour", AnalyticsEvent.created_at)
    rows = await db.execute(
        select(hour, func.count()).where(AnalyticsEvent.created_at >= since).group_by(hour)
    )
    counts = {int(value): count for value, count in rows}
    return [HourlyPointOut(hour=h, events=counts.get(h, 0)) for h in range(24)]


async def get_admin_analytics(db: AsyncSession, days: int, granularity: Granularity) -> AdminAnalyticsResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_page_views = await _count(db, AnalyticsEventType.page_view, since)
    total_project_views = await _count(db, AnalyticsEventType.project_view, since)
    github_clicks = await _count(db, AnalyticsEventType.github_click, since)
    cv_downloads = await _count(db, AnalyticsEventType.cv_download, since)
    contact_clicks = await _count(db, AnalyticsEventType.contact_click, since)
    project_link_clicks = await _count(db, AnalyticsEventType.project_link_click, since)
    language_changes = await _count(db, AnalyticsEventType.language_change, since)

    total_events = (
        await db.execute(
            select(func.count()).select_from(AnalyticsEvent).where(AnalyticsEvent.created_at >= since)
        )
    ).scalar_one()

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
            func.count(func.distinct(AnalyticsEvent.ip_hash)),
        )
        .where(AnalyticsEvent.created_at >= since)
        .group_by(bucket)
        .order_by(bucket)
    )
    timeseries = [
        TimeseriesPoint(
            date=row_bucket.date().isoformat(),
            page_views=page_views,
            unique_sessions=sessions,
            unique_visitors=visitors,
        )
        for row_bucket, page_views, sessions, visitors in timeseries_rows
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
            project_link_clicks=project_link_clicks,
            language_changes=language_changes,
            total_events=total_events,
            language_distribution=language_distribution,
        ),
        engagement=await _get_engagement(db, since),
        timeseries=timeseries,
        top_projects=top_projects,
        top_pages=await _get_top_pages(db, since),
        event_breakdown=await _get_event_breakdown(db, since),
        device_breakdown=await _get_device_breakdown(db, since),
        referrers=await _get_referrers(db, since),
        hourly_activity=await _get_hourly_activity(db, since),
        recent_events=recent_events,
    )
