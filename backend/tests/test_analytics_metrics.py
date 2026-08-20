"""Tests for the metrics the dashboard gained when the seeded demo traffic went away.

Two kinds of gap were closed and both are covered here:

*Recorded but never reported* — `metadata.path`, `project_link_click`,
`language_change` and the shape of a session (bounce, duration, return visits)
were all already in `analytics_events` and simply had no query behind them.
Those tests assert the aggregations, and they matter more than usual because
the numbers are now the *real* ones: with the synthetic rows deleted (migration
`d7a5e91c2f48`), a wrong aggregate is no longer hidden under a pile of
plausible-looking fake traffic.

*Not recorded at all* — `device_class` and `referrer_host` are new columns
written at event time. Those tests assert both the write path (classification,
the host-only guarantee) and that the read path reports only the window where
collection was actually happening, rather than folding every pre-existing row
into a giant "unknown / direct" bucket.

Unlike the other analytics test modules, this one clears `analytics_events`
around each test instead of tagging rows with a marker and deleting those.
Marker-scoped cleanup works when a test asserts a *delta* (see
test_active_visitors.py), but every assertion here is about an aggregate
computed over the whole table — a bounce rate or an average cannot be
expressed as a delta — so the table has to be the only thing in scope. Safe
because the suite runs serially against a throwaway database.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.database import async_session_factory
from app.models.analytics import AnalyticsEvent, AnalyticsEventType
from app.schemas.analytics import AnalyticsEventCreate, Granularity, sanitize_metadata
from app.services import analytics_service

CLIENT_IP = "192.0.2.7"  # RFC 5737 documentation range — never a real visitor
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


@pytest.fixture
async def db():
    async with async_session_factory() as session:
        await session.execute(delete(AnalyticsEvent))
        await session.commit()
        yield session
        await session.execute(delete(AnalyticsEvent))
        await session.commit()


async def _add(
    db,
    session_id: str,
    *,
    event_type: AnalyticsEventType = AnalyticsEventType.page_view,
    minutes_ago: float = 1,
    path: str | None = None,
    device_class: str | None = analytics_service.DEVICE_DESKTOP,
    referrer_host: str | None = None,
    project_slug: str | None = None,
) -> None:
    """Insert one event directly. Bypasses `record_event` on purpose: these are
    read-path tests, and going through the write path would drag in bot
    filtering, dedup windows and rate limits that have their own tests.
    """
    db.add(
        AnalyticsEvent(
            event_type=event_type,
            session_id=session_id,
            project_slug=project_slug,
            event_metadata={"path": path} if path else None,
            ip_hash=f"hash-{session_id}",
            device_class=device_class,
            referrer_host=referrer_host,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
    )
    await db.commit()


async def _analytics(db, days: int = 30):
    return await analytics_service.get_admin_analytics(db, days=days, granularity=Granularity.day)


# --------------------------------------------------------------------------
# Device classification — the write path
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_agent,expected",
    [
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
            analytics_service.DEVICE_MOBILE,
        ),
        (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36",
            analytics_service.DEVICE_MOBILE,
        ),
        # iPad Safari's UA carries a "Mobile/" token, so a naive mobile-first
        # test files every tablet as a phone. Tablet rules run first for this.
        (
            "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
            analytics_service.DEVICE_TABLET,
        ),
        # Android tablets are identified by the ABSENCE of "Mobile".
        (
            "Mozilla/5.0 (Linux; Android 13; SM-X200) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
            analytics_service.DEVICE_TABLET,
        ),
        (BROWSER_UA, analytics_service.DEVICE_DESKTOP),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
            analytics_service.DEVICE_DESKTOP,
        ),
        (None, analytics_service.DEVICE_UNKNOWN),
        ("", analytics_service.DEVICE_UNKNOWN),
    ],
)
def test_device_classification(user_agent, expected):
    assert analytics_service.classify_device(user_agent) == expected


async def test_recording_an_event_stores_the_device_class(db):
    await analytics_service.record_event(
        db,
        AnalyticsEventCreate(event_type=AnalyticsEventType.page_view, session_id=f"dev-{uuid.uuid4().hex}"),
        CLIENT_IP,
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148",
    )

    stored = (await db.execute(select(AnalyticsEvent))).scalars().all()
    assert [row.device_class for row in stored] == [analytics_service.DEVICE_MOBILE]


async def test_a_request_with_no_user_agent_is_recorded_as_unknown_not_null(db):
    """NULL means "written before the column existed" and the device/referrer
    breakdowns key on that. A live request with no UA header must therefore
    still carry a value, or it would be silently excluded from its own report.
    """
    await analytics_service.record_event(
        db,
        AnalyticsEventCreate(event_type=AnalyticsEventType.page_view, session_id=f"noua-{uuid.uuid4().hex}"),
        CLIENT_IP,
        None,
    )

    stored = (await db.execute(select(AnalyticsEvent))).scalars().all()
    assert [row.device_class for row in stored] == [analytics_service.DEVICE_UNKNOWN]


# --------------------------------------------------------------------------
# Referrer — host only, and out of metadata into its own column
# --------------------------------------------------------------------------


def test_a_full_referrer_url_is_dropped_not_stored():
    """The frontend sends `URL.hostname`, but the allowlist must not depend on
    that: anyone can post to this endpoint. A whole URL carries a path and query
    string — where a search term or an address would live — so it is rejected
    outright rather than trimmed.
    """
    assert sanitize_metadata({"ref": "https://www.google.com/search?q=someone%40example.com"}) is None


def test_a_referrer_host_is_kept_and_case_folded():
    assert sanitize_metadata({"ref": "News.Ycombinator.com"}) == {"ref": "news.ycombinator.com"}


async def test_the_referrer_moves_out_of_metadata_into_its_own_column(db):
    await analytics_service.record_event(
        db,
        AnalyticsEventCreate(
            event_type=AnalyticsEventType.page_view,
            session_id=f"ref-{uuid.uuid4().hex}",
            metadata={"path": "/", "ref": "linkedin.com"},
        ),
        CLIENT_IP,
        BROWSER_UA,
    )

    row = (await db.execute(select(AnalyticsEvent))).scalars().one()
    assert row.referrer_host == "linkedin.com"
    assert row.event_metadata == {"path": "/"}, "ref was duplicated into metadata instead of moved"


# --------------------------------------------------------------------------
# Aggregations that existed as data but never as a query
# --------------------------------------------------------------------------


async def test_top_pages_groups_page_views_by_path(db):
    await _add(db, "s1", path="/projects")
    await _add(db, "s2", path="/projects")
    await _add(db, "s3", path="/skills")
    # Not a page_view, so it must not land in a *pages* report even though it
    # carries a path.
    await _add(db, "s4", event_type=AnalyticsEventType.contact_click, path="/contact")

    top_pages = (await _analytics(db)).top_pages

    assert [(page.path, page.views, page.unique_sessions) for page in top_pages] == [
        ("/projects", 2, 2),
        ("/skills", 1, 1),
    ]


async def test_the_two_previously_invisible_event_types_are_counted(db):
    """`project_link_click` and `language_change` were recorded from the start
    and reported by nothing — the dashboard summarised five of seven types.
    """
    await _add(db, "s1", event_type=AnalyticsEventType.project_link_click)
    await _add(db, "s1", event_type=AnalyticsEventType.language_change)
    await _add(db, "s2", event_type=AnalyticsEventType.language_change)

    summary = (await _analytics(db)).summary

    assert summary.project_link_clicks == 1
    assert summary.language_changes == 2
    assert summary.total_events == 3


async def test_event_breakdown_zero_fills_every_type(db):
    await _add(db, "s1", event_type=AnalyticsEventType.page_view)

    breakdown = (await _analytics(db)).event_breakdown
    counts = {entry.event_type: entry.count for entry in breakdown}

    assert len(breakdown) == len(AnalyticsEventType), "a type with no events was omitted"
    assert counts["page_view"] == 1
    assert counts["cv_download"] == 0


async def test_hourly_activity_always_has_24_buckets(db):
    await _add(db, "s1")

    hourly = (await _analytics(db)).hourly_activity

    assert [point.hour for point in hourly] == list(range(24))
    assert sum(point.events for point in hourly) == 1


async def test_timeseries_reports_unique_visitors_from_ip_hash(db):
    await _add(db, "s1", minutes_ago=5)
    await _add(db, "s2", minutes_ago=5)
    await _add(db, "s1", minutes_ago=4)  # same visitor again — still one

    timeseries = (await _analytics(db)).timeseries

    assert sum(point.unique_visitors for point in timeseries) == 2


# --------------------------------------------------------------------------
# Engagement — session-shaped metrics
# --------------------------------------------------------------------------


async def test_bounce_rate_counts_one_page_view_and_nothing_else(db):
    await _add(db, "bounced")
    await _add(db, "engaged", minutes_ago=10)
    await _add(db, "engaged", event_type=AnalyticsEventType.cv_download, minutes_ago=9)

    engagement = (await _analytics(db)).engagement

    assert engagement.bounce_rate == 0.5


async def test_average_duration_ignores_single_event_sessions(db):
    """A one-event session has a duration of exactly zero by construction, not
    because the visitor left instantly. Averaging it in would restate the bounce
    rate as a time and drag every real reading toward zero.
    """
    await _add(db, "single")
    await _add(db, "double", minutes_ago=10)
    await _add(db, "double", minutes_ago=9, event_type=AnalyticsEventType.project_view)

    engagement = (await _analytics(db)).engagement

    assert engagement.avg_session_duration_seconds == pytest.approx(60, abs=1)


async def test_returning_sessions_need_activity_on_more_than_one_day(db):
    await _add(db, "same-day", minutes_ago=5)
    await _add(db, "same-day", minutes_ago=6)
    await _add(db, "came-back", minutes_ago=5)
    await _add(db, "came-back", minutes_ago=25 * 60)  # 25h guarantees a date change

    engagement = (await _analytics(db)).engagement

    assert engagement.returning_sessions == 1


async def test_engagement_is_zero_rather_than_undefined_on_an_empty_table(db):
    engagement = (await _analytics(db)).engagement

    assert engagement.bounce_rate == 0.0
    assert engagement.avg_session_duration_seconds == 0.0
    assert engagement.returning_sessions == 0


# --------------------------------------------------------------------------
# The collection window — new columns must not misreport old rows
# --------------------------------------------------------------------------


async def test_device_breakdown_counts_sessions_not_events(db):
    await _add(db, "phone", device_class=analytics_service.DEVICE_MOBILE)
    await _add(db, "phone", device_class=analytics_service.DEVICE_MOBILE, minutes_ago=2)
    await _add(db, "phone", device_class=analytics_service.DEVICE_MOBILE, minutes_ago=3)
    await _add(db, "laptop", device_class=analytics_service.DEVICE_DESKTOP)

    breakdown = (await _analytics(db)).device_breakdown

    assert {entry.device_class: entry.sessions for entry in breakdown} == {"mobile": 1, "desktop": 1}


async def test_rows_from_before_the_column_existed_are_excluded(db):
    """A NULL device_class is a row written by the previous build. Counting it
    would report a large "unknown device, direct traffic" cohort that is really
    just "we were not measuring yet" — the one reading that would make both new
    charts actively misleading on the day they ship.
    """
    await _add(db, "legacy-1", device_class=None)
    await _add(db, "legacy-2", device_class=None)
    await _add(db, "current", device_class=analytics_service.DEVICE_DESKTOP)

    report = await _analytics(db)

    assert sum(entry.sessions for entry in report.device_breakdown) == 1
    assert sum(entry.sessions for entry in report.referrers) == 1
    # …while the metrics that were always collectable still see every row.
    assert report.summary.total_events == 3


async def test_a_session_is_attributed_to_one_referrer_not_every_event(db):
    """The referrer rides only the first page_view of a session. Grouping events
    rather than sessions would file every subsequent click under "direct" and
    bury the real source under its own traffic.
    """
    await _add(db, "from-linkedin", referrer_host="linkedin.com", minutes_ago=10)
    await _add(db, "from-linkedin", minutes_ago=9)
    await _add(db, "from-linkedin", minutes_ago=8, event_type=AnalyticsEventType.project_view)
    await _add(db, "typed-it", minutes_ago=7)

    referrers = {entry.host: entry.sessions for entry in (await _analytics(db)).referrers}

    assert referrers == {"linkedin.com": 1, analytics_service.DIRECT_REFERRER: 1}
