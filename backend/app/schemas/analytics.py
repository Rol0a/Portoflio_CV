"""Analytics wire schema — and the boundary that keeps it performance-only.

`architecture.md` §9 and `docs/security.md` §9 promise the site collects
"no PII". Until this module enforced it, that promise was held up by the
*frontend* choosing to send well-behaved fields: `metadata` was a bare
`dict`, so `POST /api/v1/analytics/events` — a public, unauthenticated
endpoint reachable by anyone with curl — accepted arbitrary JSON and wrote
it verbatim into the `analytics_events.metadata` JSONB column.

`tests/test_analytics_privacy.py::test_stored_row_carries_no_free_text_from_the_visitor`
asserted the stored shape was `{"path"}` only, but it asserted that about a
row *the test itself constructed*. Nothing stopped a third party from
posting `{"email": "...", "notes": "<free text>"}` and having it persisted.
A stranger could have used this portfolio's own database as a scratchpad for
personal data, and every "we store no PII" claim in the docs would have been
quietly false.

So the rule here is an **allowlist, not a blocklist**: a key that is not
named below is dropped, and a value that does not match its declared shape
is dropped with it. Adding a new tracked dimension therefore requires
editing this file, which is exactly the review checkpoint the privacy
commitment needs.

Sanitising rather than rejecting is deliberate. These events arrive from a
fire-and-forget beacon that cannot react to a 4xx (see `routes/analytics.py`),
and a hard 422 would turn a stray field into lost measurement. Dropping the
offending key keeps the countable part of the event — which is the only part
that was ever wanted.
"""

import enum
import re

from pydantic import BaseModel, field_validator

from app.models.analytics import AnalyticsEventType
from app.models.project import Locale


class Granularity(str, enum.Enum):
    day = "day"
    week = "week"
    month = "month"


# --- The allowlist ---------------------------------------------------------
#
# Every key the frontend actually sends, enumerated from its call sites:
#   path       — App.tsx, on page_view
#   from / to  — LanguageSwitcher.tsx, on language_change (locale codes)
#   link       — ProjectDetail.tsx, on project_link_click ("demo")
#   ref        — hooks/useAnalytics.ts, on the session's first page_view
#
# Note this is wider than the set the privacy test previously asserted
# (`{"path"}`); that assertion passed only because the test never exercised
# the language_change or project_link_click paths. The allowlist matches
# what the application really does, which is the point of enumerating it.

# A route path and nothing more. Query strings and fragments are stripped
# before this runs (see `_clean_path`) because that is where free text
# actually arrives — `/contact?email=someone@example.com` is a real way for
# an address to end up in the analytics table without anyone intending it.
PATH_PATTERN = re.compile(r"^/[A-Za-z0-9/_.-]{0,199}$")

# BCP-47-ish language tags: "en", "es", "pt-BR". Bounded hard — a locale code
# is never long, so anything long is not a locale code.
LOCALE_CODE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")

# A short interaction token chosen by our own code, not typed by anyone.
LINK_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

# A referrer's *host* and nothing else. The frontend parses `document.referrer`
# and sends only `URL.hostname`, so the path and query string — the halves that
# can carry a search term, a session token, or an email address — never leave
# the browser. This pattern is the server-side half of that guarantee: it
# rejects anything containing `/`, `?`, `:` or whitespace, so a client that
# sent a whole URL gets the key dropped rather than stored. 253 chars is the
# DNS maximum for a fully-qualified name.
REFERRER_HOST_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")

METADATA_ALLOWLIST: dict[str, re.Pattern[str]] = {
    "path": PATH_PATTERN,
    "from": LOCALE_CODE_PATTERN,
    "to": LOCALE_CODE_PATTERN,
    "link": LINK_TOKEN_PATTERN,
    "ref": REFERRER_HOST_PATTERN,
}

# The client generates this itself (`crypto.randomUUID()` in
# hooks/useAnalytics.ts). It is an opaque grouping key, so the only things
# that matter are that it is bounded and cannot carry prose: no spaces, no
# "@", no ".", so neither a sentence nor an email address fits.
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# Slugs are looked up against the projects table, so an unmatched value is
# harmless — but it is still stored verbatim in `project_slug`, so it gets
# the same bounded treatment as everything else.
PROJECT_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def _clean_path(value: str) -> str | None:
    """Strip the parts of a URL path that can carry free text, then validate.

    Splitting on `?` and `#` first (rather than rejecting paths containing
    them) keeps the useful half of a real navigation: `/projects?ref=x` still
    counts as a view of `/projects`, while `ref=x` — the part that could hold
    anything at all — never reaches the database.
    """
    cleaned = value.split("?", 1)[0].split("#", 1)[0]
    return cleaned if PATH_PATTERN.fullmatch(cleaned) else None


def sanitize_metadata(metadata: dict | None) -> dict | None:
    """Reduce arbitrary client JSON to the allowlisted, well-shaped subset.

    Returns None rather than `{}` when nothing survives, so a scrubbed event
    is stored identically to one that never carried metadata — there is no
    residual signal that something was dropped, and no empty object to
    special-case downstream.
    """
    if not metadata:
        return None

    kept: dict[str, str] = {}
    for key, pattern in METADATA_ALLOWLIST.items():
        value = metadata.get(key)
        # Only strings are ever accepted: a nested dict or list is a way to
        # smuggle in a payload the flat patterns below would never see.
        if not isinstance(value, str):
            continue
        if key == "path":
            path = _clean_path(value)
            if path is not None:
                kept[key] = path
        elif key == "ref":
            # Hostnames are case-insensitive, and folding here rather than
            # trusting the client keeps "Google.com" and "google.com" from
            # becoming two rows in the referrer breakdown.
            host = value.lower()
            if pattern.fullmatch(host):
                kept[key] = host
        elif pattern.fullmatch(value):
            kept[key] = value

    return kept or None


class AnalyticsEventCreate(BaseModel):
    event_type: AnalyticsEventType
    session_id: str
    project_slug: str | None = None
    locale: Locale | None = None
    metadata: dict | None = None

    @field_validator("session_id")
    @classmethod
    def _bound_session_id(cls, value: str) -> str:
        """Blank out an unusable session id instead of raising.

        `analytics_service.record_event` already drops events with no
        session_id (returning "ignored"), so normalising to "" routes a
        malformed id through that same, already-tested path — and keeps the
        endpoint's fire-and-forget 200 contract intact for a beacon that
        cannot handle a 422.
        """
        return value if SESSION_ID_PATTERN.fullmatch(value) else ""

    @field_validator("project_slug")
    @classmethod
    def _bound_project_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value if PROJECT_SLUG_PATTERN.fullmatch(value) else None

    @field_validator("metadata")
    @classmethod
    def _allowlist_metadata(cls, value: dict | None) -> dict | None:
        return sanitize_metadata(value)


class AnalyticsEventResponse(BaseModel):
    status: str


class AnalyticsSummary(BaseModel):
    total_page_views: int
    unique_sessions: int
    total_project_views: int
    github_clicks: int
    cv_downloads: int
    contact_clicks: int
    # Both of these were already being *recorded* and never reported: the
    # dashboard counted five of the seven event types, so a visitor opening a
    # live demo or switching to Spanish left no visible trace.
    project_link_clicks: int
    language_changes: int
    total_events: int
    language_distribution: dict[str, int]


class EngagementSummary(BaseModel):
    """Session-shaped metrics — how much a visit contained, not how many
    visits there were. Every field is derived from `analytics_events` rows
    that were already being stored; none of it needed new collection, it
    needed a query nobody had written.
    """

    # Fraction (0-1) of sessions whose entire footprint is one page_view: they
    # arrived, looked at one page, and did nothing else measurable.
    bounce_rate: float
    pages_per_session: float
    avg_events_per_session: float
    # Averaged over sessions with more than one event only. A single-event
    # session has a duration of exactly zero by construction, not because the
    # visitor left instantly, so including them would just restate the bounce
    # rate as a time.
    avg_session_duration_seconds: float
    # Sessions that appear on more than one distinct UTC day. localStorage
    # holds the session id indefinitely, so this is "came back later", not
    # "reloaded the tab".
    returning_sessions: int


class TimeseriesPoint(BaseModel):
    date: str
    page_views: int
    unique_sessions: int
    # Distinct `ip_hash` in the bucket. The salt rotates daily
    # (`hash_ip_daily`), so this is exact at day granularity and becomes
    # visitor-*days* at week/month — the frontend only ever requests `day`.
    unique_visitors: int


class TopProjectOut(BaseModel):
    slug: str
    title: str
    views: int


class TopPageOut(BaseModel):
    path: str
    views: int
    unique_sessions: int


class EventCountOut(BaseModel):
    event_type: str
    count: int


class DeviceCountOut(BaseModel):
    device_class: str
    sessions: int


class ReferrerCountOut(BaseModel):
    host: str
    sessions: int


class HourlyPointOut(BaseModel):
    hour: int
    events: int


class RecentEventOut(BaseModel):
    event_type: str
    project_slug: str | None
    timestamp: str


class AdminAnalyticsResponse(BaseModel):
    summary: AnalyticsSummary
    engagement: EngagementSummary
    timeseries: list[TimeseriesPoint]
    top_projects: list[TopProjectOut]
    top_pages: list[TopPageOut]
    event_breakdown: list[EventCountOut]
    device_breakdown: list[DeviceCountOut]
    referrers: list[ReferrerCountOut]
    hourly_activity: list[HourlyPointOut]
    recent_events: list[RecentEventOut]
