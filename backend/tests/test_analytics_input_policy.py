"""What the public analytics endpoint will and will not accept into the database.

`POST /api/v1/analytics/events` is unauthenticated and reachable by anyone —
that is the point of a beacon. Until `app/schemas/analytics.py` grew an
allowlist, its `metadata` field was a bare `dict`, so "anyone" included anyone
with curl, and whatever they sent was written verbatim into a JSONB column on
a site whose documentation promises it stores no personal data.

`test_analytics_privacy.py` asserted the stored metadata shape was `{"path"}`,
but only for rows it built itself, so it could not have caught this. These
tests come at it from the other side: they hand the schema the payloads a
hostile or careless client would actually send and require the policy to
strip them.

Pure schema-level tests — no database, no event loop, no fixtures. The
boundary being tested runs before any of that.
"""

import pytest

from app.models.analytics import AnalyticsEventType
from app.schemas.analytics import AnalyticsEventCreate, sanitize_metadata

VALID_SESSION = "3f8a1b0c-7d2e-4a55-9c31-0e6b8d4f2a17"  # crypto.randomUUID() shape


def build(**kwargs) -> AnalyticsEventCreate:
    return AnalyticsEventCreate(
        event_type=kwargs.pop("event_type", AnalyticsEventType.page_view),
        session_id=kwargs.pop("session_id", VALID_SESSION),
        **kwargs,
    )


# --------------------------------------------------------------------------
# metadata — allowlisted, not merely filtered
# --------------------------------------------------------------------------


def test_the_keys_the_frontend_really_sends_all_survive():
    """The floor: enumerated from the actual call sites (App.tsx sends `path`,
    LanguageSwitcher sends `from`/`to`, ProjectDetail sends `link`). A policy
    that silently dropped one of these would quietly stop measuring a feature.
    """
    assert sanitize_metadata({"path": "/projects"}) == {"path": "/projects"}
    assert sanitize_metadata({"from": "en", "to": "es"}) == {"from": "en", "to": "es"}
    assert sanitize_metadata({"link": "demo"}) == {"link": "demo"}


@pytest.mark.parametrize(
    "hostile",
    [
        {"email": "someone@example.com"},
        {"name": "A Real Person"},
        {"message": "free text a visitor typed into something"},
        {"notes": "arbitrary", "phone": "+1 555 0100"},
        {"fingerprint": "canvas:9f2b...", "referrer": "https://example.com/inbox"},
    ],
)
def test_unlisted_keys_are_dropped_entirely(hostile):
    """The core of the fix. None of these keys are in the allowlist, so none of
    them reach the database — regardless of what the sender intended.
    """
    assert sanitize_metadata(hostile) is None


def test_an_unlisted_key_alongside_a_valid_one_does_not_ride_along():
    """The realistic shape of the attack: bury the payload next to a field
    that legitimately belongs, and hope the check is per-request rather than
    per-key.
    """
    assert sanitize_metadata({"path": "/contact", "email": "someone@example.com"}) == {
        "path": "/contact"
    }


def test_a_query_string_is_stripped_from_the_path():
    """Where PII arrives without anyone meaning it to: `/contact?email=...` is
    an ordinary URL, and storing the path verbatim would store the address.
    The navigation still counts — only the parameters are discarded.
    """
    assert sanitize_metadata({"path": "/contact?email=someone@example.com"}) == {
        "path": "/contact"
    }


def test_a_fragment_is_stripped_from_the_path():
    assert sanitize_metadata({"path": "/projects#notes-about-someone"}) == {"path": "/projects"}


def test_an_overlong_path_is_dropped_rather_than_truncated():
    """Truncating would keep a prefix of whatever was sent. Dropping keeps
    nothing — the event still counts, it just carries no path.
    """
    assert sanitize_metadata({"path": "/" + "a" * 500}) is None


@pytest.mark.parametrize(
    "not_a_path",
    ["https://example.com/exfil", "no-leading-slash", "/path with spaces", "/contact\n\rX"],
)
def test_values_that_are_not_route_paths_are_dropped(not_a_path):
    assert sanitize_metadata({"path": not_a_path}) is None


@pytest.mark.parametrize("smuggled", [{"path": {"nested": "payload"}}, {"path": ["a", "b"]}, {"path": 42}])
def test_non_string_values_are_dropped(smuggled):
    """JSONB accepts nested structures, so a dict or list under an allowlisted
    key would otherwise pass a key-name check and store an arbitrary payload.
    """
    assert sanitize_metadata(smuggled) is None


def test_nothing_surviving_is_stored_as_none_not_an_empty_object():
    """A scrubbed event must be indistinguishable from one that never carried
    metadata — no empty `{}` left behind as a marker that something was
    removed.
    """
    assert sanitize_metadata({"email": "someone@example.com"}) is None
    assert build(metadata={"email": "someone@example.com"}).metadata is None


def test_the_policy_applies_through_the_schema_not_just_the_helper():
    """The helper is only useful if the wire schema actually calls it — this
    asserts the validator is wired, which is the part a refactor would break.
    """
    event = build(metadata={"path": "/contact?email=someone@example.com", "ssn": "000-00-0000"})
    assert event.metadata == {"path": "/contact"}


# --------------------------------------------------------------------------
# session_id — an opaque grouping key, not a place to put text
# --------------------------------------------------------------------------


def test_a_normal_session_id_is_kept():
    assert build().session_id == VALID_SESSION


@pytest.mark.parametrize(
    "hostile",
    [
        "someone@example.com",
        "a sentence a visitor typed",
        "x" * 400,
        "short",
        "<script>alert(1)</script>",
    ],
)
def test_an_unusable_session_id_is_blanked_so_the_event_is_ignored(hostile):
    """Blanked rather than rejected: `analytics_service.record_event` already
    drops events with no session_id, and the endpoint must keep answering 200
    to a beacon that cannot react to a 4xx. The event is discarded either way —
    this just reuses the tested path to do it.
    """
    assert build(session_id=hostile).session_id == ""


# --------------------------------------------------------------------------
# project_slug — stored verbatim, so bounded like everything else
# --------------------------------------------------------------------------


def test_a_real_slug_is_kept():
    assert build(project_slug="quadruped-robot").project_slug == "quadruped-robot"


@pytest.mark.parametrize(
    "hostile",
    ["Someone's Name", "../../etc/passwd", "slug with spaces", "x" * 300, "UPPERCASE"],
)
def test_a_malformed_slug_is_discarded(hostile):
    """Unmatched slugs are already harmless for the foreign-key lookup, but the
    raw value is still written to `analytics_events.project_slug` — so it gets
    the same bounded, charset-limited treatment as every other stored field.
    """
    assert build(project_slug=hostile).project_slug is None
