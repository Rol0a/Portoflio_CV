"""In-process, IP-keyed sliding-window rate limiting.

Two endpoints need a limit keyed on something the *client cannot choose*:

- `POST /api/v1/contact` sends real email. Without a limit it is an open spam
  relay pointed at the site owner's inbox.
- `POST /api/v1/analytics/events` already limits 60 events/minute, but keys on
  `payload.session_id` — which the client supplies. Rotating it per request
  bypasses the cap completely and writes unbounded rows (M16). An IP-keyed
  limit in front of the session-keyed one closes that.

Both depend on `client_ip()` returning the real visitor address, which is only
true because of the proxy-header work in `app/middleware/proxy.py` — behind
Caddy every caller would otherwise share one bucket.

**Why in-memory rather than a database table.** A persistent limiter would mean
writing a row per visitor request, i.e. building exactly the per-visitor
request history that `architecture.md` §9 promises not to keep — and then
needing its own retention policy. Counters here live in memory, are never
written to disk, and vanish on restart. The cost is that a restart resets every
window and a second replica would have its own counters; this deployment runs
one backend replica (docker-compose.yml), and the abuse this defends against is
automated flooding, which a restart does not help an attacker perform.

Addresses are stored hashed, so a memory dump or traceback cannot reveal who
has been visiting.
"""

import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class RateLimit:
    """`max_events` permitted per `window_seconds`, per client."""

    max_events: int
    window_seconds: int


# One email per 5 minutes, five per hour: generous for a person with something
# to say, useless for a script. Enforced as two windows because a single
# hourly cap would still allow five messages in five seconds.
CONTACT_BURST = RateLimit(max_events=1, window_seconds=300)
CONTACT_HOURLY = RateLimit(max_events=5, window_seconds=3600)

# Deliberately well above the 60/minute session-keyed analytics limit: this is
# a backstop against session-id rotation, not the primary control, and one IP
# can legitimately carry several real visitors behind a shared network.
ANALYTICS_PER_IP = RateLimit(max_events=300, window_seconds=60)

# Bounds memory: an attacker cycling source addresses would otherwise grow the
# map without limit. Once exceeded, the least recently seen keys are dropped —
# which forgives them, but forgetting an idle client is the safe failure here.
MAX_TRACKED_CLIENTS = 10_000

_hits: defaultdict[tuple[str, str], deque[float]] = defaultdict(deque)


def _key(scope: str, client_ip: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{client_ip}:{settings.session_secret_key}".encode()).hexdigest()
    return (scope, digest)


def _evict_if_oversized() -> None:
    if len(_hits) <= MAX_TRACKED_CLIENTS:
        return
    oldest = sorted(_hits.items(), key=lambda item: item[1][-1] if item[1] else 0.0)
    for key, _ in oldest[: len(_hits) - MAX_TRACKED_CLIENTS]:
        del _hits[key]


def check(scope: str, client_ip: str, *limits: RateLimit) -> int | None:
    """Seconds the caller must wait, or None if the request may proceed.

    Read-only: call `record()` once the request is actually accepted, so a
    rejected request does not extend its own penalty.
    """
    now = time.monotonic()
    timestamps = _hits[_key(scope, client_ip)]

    longest = max(limit.window_seconds for limit in limits)
    while timestamps and now - timestamps[0] > longest:
        timestamps.popleft()

    for limit in limits:
        cutoff = now - limit.window_seconds
        recent = sum(1 for stamp in timestamps if stamp > cutoff)
        if recent >= limit.max_events:
            oldest_in_window = next(stamp for stamp in timestamps if stamp > cutoff)
            return max(1, int(limit.window_seconds - (now - oldest_in_window)))

    return None


def record(scope: str, client_ip: str) -> None:
    _hits[_key(scope, client_ip)].append(time.monotonic())
    _evict_if_oversized()


def reset() -> None:
    """Clear all counters. For tests only."""
    _hits.clear()
