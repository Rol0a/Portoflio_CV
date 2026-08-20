"""The backend's own exposure rules, independent of the Caddyfile.

`infrastructure/caddy/Caddyfile` is the primary control that keeps
`/internal/*` and the admin surface off the public path, and
`scripts/preflight.sh` asserts its deny rules are present. But a config file
checked at deploy time cannot protect a backend that is later reached some
other way — a repointed tunnel ingress rule, a `docker compose up` without the
caddy service, a deleted `handle` block.

`app/middleware/exposure.py` is the second lock, and this file is what keeps
it honest. These tests deliberately do **not** go through Caddy: they speak
ASGI straight to the middleware, which is exactly the situation the guard
exists for.

No database is touched — the guard runs before any route does, so a probe app
with trivial handlers exercises it completely (same approach as
test_proxy_headers.py).
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.exposure import DEFAULT_ADMIN_ENTRY, ExposureGuardMiddleware

# Somewhere on portfolio-net, i.e. how the noc container appears to the backend.
IN_NETWORK_PEER = "172.20.0.9"
# A genuinely globally-routable address — what the peer looks like if the
# backend is ever reached without a proxy in front of it at all.
#
# Deliberately NOT one of the RFC 5737 documentation ranges used elsewhere in
# this suite: Python's `ipaddress` reports 192.0.2.0/24, 198.51.100.0/24 and
# 203.0.113.0/24 as `is_private`, because IANA lists them as not globally
# reachable. Using one here would make the guard's private-peer check pass and
# the test assert nothing.
PUBLIC_PEER = "93.184.216.34"

# Only ever used as an X-Forwarded-For *value*, never as a peer, so the
# documentation range is fine.
VISITOR = "198.51.100.7"

SECRET_ENTRY = "d4b9f1c2a7e6"

GUARDED_ADMIN_PATHS = [
    "/api/v1/admin/analytics",
    "/api/v1/auth/login",
    "/admin",
    "/admin/dashboard",
]


def build_probe_app(admin_entry: str | None = None) -> FastAPI:
    """The guard in front of routes that always succeed, so any non-200 in
    these tests is the guard's doing and nothing else's.
    """
    probe = FastAPI()

    @probe.get("/{full_path:path}")
    async def catch_all() -> dict:
        return {"reached": True}

    probe.add_middleware(ExposureGuardMiddleware, admin_entry=admin_entry)
    return probe


async def get(
    path: str,
    peer: str = IN_NETWORK_PEER,
    forwarded_for: str | None = None,
    entry: str | None = None,
    funnel: str | None = None,
    admin_entry: str | None = None,
) -> int:
    """Status code for one request, described the way the guard sees it:
    who the peer is, whether anything proxied it, and how it was marked.
    """
    headers = {}
    if forwarded_for is not None:
        headers["x-forwarded-for"] = forwarded_for
    if entry is not None:
        headers["x-portfolio-entry"] = entry
    if funnel is not None:
        headers["tailscale-funnel-request"] = funnel

    transport = ASGITransport(app=build_probe_app(admin_entry), client=(peer, 0))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path, headers=headers)
    return response.status_code


# --------------------------------------------------------------------------
# Rule 1 — /internal/* is for unproxied, in-network callers only
# --------------------------------------------------------------------------


async def test_noc_can_still_read_internal_metrics():
    """The one call path that must keep working: the noc container reaching
    http://backend:8000/internal/metrics directly over the Docker network.
    A guard that broke this would take the Network Health dashboard down.
    """
    assert await get("/internal/metrics") == 200


async def test_internal_metrics_is_refused_when_proxied():
    """The regression this exists for. If Caddy's `handle /internal/*` deny
    were deleted, the request would arrive here proxied — and be refused
    anyway. Any proxy sets X-Forwarded-For, so this covers Caddy, cloudflared,
    and anything else placed in front.
    """
    assert await get("/internal/metrics", forwarded_for=VISITOR) == 404


async def test_internal_metrics_is_refused_from_a_public_peer():
    """Belt and braces for the unproxied case: a direct connection from a
    routable address means the backend's port got published to the internet,
    which docker-compose.yml never does. Refuse rather than trust it.
    """
    assert await get("/internal/metrics", peer=PUBLIC_PEER) == 404


async def test_the_refusal_is_a_404_not_a_403():
    """403 would confirm the endpoint exists. Matching Caddy's `respond 404`
    keeps the public answer identical to that of any nonexistent path.
    """
    assert await get("/internal/metrics", forwarded_for=VISITOR) == 404


# --------------------------------------------------------------------------
# Rule 2 — admin surfaces need proof of admin entry, once proxied
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", GUARDED_ADMIN_PATHS)
async def test_admin_surface_is_refused_when_marked_public(path):
    """The Caddy public block stamps `X-Portfolio-Entry: public`. Even if its
    deny rules were removed and the request fell through to the generic
    `handle /api/*`, it still cannot reach the admin surface.
    """
    assert await get(path, forwarded_for=VISITOR, entry="public") == 404


@pytest.mark.parametrize("path", GUARDED_ADMIN_PATHS)
async def test_admin_surface_is_refused_when_caddy_is_bypassed_entirely(path):
    """The case a "marked public → refuse" rule would miss, and the reason the
    check is written the other way round. A tunnel repointed straight at
    backend:8000 produces a proxied request (cloudflared adds
    X-Forwarded-For) carrying no entry marker at all — with Caddy gone, there
    is nothing left to stamp one.
    """
    assert await get(path, forwarded_for=VISITOR, entry=None) == 404


@pytest.mark.parametrize("path", GUARDED_ADMIN_PATHS)
async def test_admin_surface_is_reachable_through_the_admin_entry_point(path):
    """The guard must not lock the owner out of their own dashboard: a request
    proxied by Caddy's Tailscale-bound admin block carries the marker and
    passes straight through.
    """
    assert await get(path, forwarded_for=VISITOR, entry=DEFAULT_ADMIN_ENTRY) == 200


@pytest.mark.parametrize("path", GUARDED_ADMIN_PATHS)
async def test_admin_surface_is_reachable_unproxied(path):
    """Dev, the test client, and direct in-network calls have no proxy in
    front and are judged only by rule 1. Nothing publishes the backend's port
    (docker-compose.yml), so an unproxied request cannot originate outside.
    """
    assert await get(path) == 200


async def test_ordinary_public_api_traffic_is_untouched():
    """The guard is narrow on purpose. A visitor loading the portfolio hits
    /api/v1/projects through the public block, marked public — and must be
    served normally.
    """
    assert await get("/api/v1/projects", forwarded_for=VISITOR, entry="public") == 200


# --------------------------------------------------------------------------
# ADMIN_ENTRY_TOKEN — turning a known marker into a shared secret
# --------------------------------------------------------------------------


async def test_configured_token_rejects_the_default_marker():
    """With a token set, guessing the constant from the source is no longer
    enough — this is the difference between defending against a Caddy
    misconfiguration and defending against someone already past Caddy.
    """
    status = await get(
        "/api/v1/admin/analytics",
        forwarded_for=VISITOR,
        entry=DEFAULT_ADMIN_ENTRY,
        admin_entry=SECRET_ENTRY,
    )
    assert status == 404


async def test_configured_token_admits_the_matching_marker():
    status = await get(
        "/api/v1/admin/analytics",
        forwarded_for=VISITOR,
        entry=SECRET_ENTRY,
        admin_entry=SECRET_ENTRY,
    )
    assert status == 200


async def test_internal_paths_are_not_rescued_by_a_valid_admin_marker():
    """The two rules are independent, and rule 1 is the stricter one:
    /internal/* is never proxied by anything, so even a correctly marked admin
    request must not reach it. Caddy's admin block denies it too — this is the
    app-side half of that.
    """
    status = await get(
        "/internal/metrics",
        forwarded_for=VISITOR,
        entry=SECRET_ENTRY,
        admin_entry=SECRET_ENTRY,
    )
    assert status == 404


# --------------------------------------------------------------------------
# Rule 0 — Tailscale's own Funnel marker
# --------------------------------------------------------------------------

# Tailscale sets this on every request entering through Funnel, i.e. from the
# public internet. Verified against the live ingress: a client sending "?0"
# had it rewritten to "?1", so it cannot be forged away.
FUNNEL_ON = "?1"


@pytest.mark.parametrize("path", GUARDED_ADMIN_PATHS + ["/internal/metrics"])
async def test_funnel_requests_are_refused_on_every_non_public_surface(path):
    """The outermost rule. Tailscale says this came from the public internet,
    so no admin or internal path may serve it — whatever else is true about
    the request.
    """
    assert await get(path, forwarded_for=VISITOR, entry=None, funnel=FUNNEL_ON) == 404


@pytest.mark.parametrize("path", GUARDED_ADMIN_PATHS)
async def test_a_valid_admin_marker_cannot_rescue_a_funnel_request(path):
    """The point of layering the signals rather than checking one. Even if the
    entry marker were somehow correct — a Caddyfile that stamped the admin
    value on the public block, say — Tailscale's evidence still wins, because
    it is the only signal this project does not generate itself.
    """
    status = await get(
        path,
        forwarded_for=VISITOR,
        entry=SECRET_ENTRY,
        funnel=FUNNEL_ON,
        admin_entry=SECRET_ENTRY,
    )
    assert status == 404


async def test_ordinary_public_traffic_over_funnel_is_still_served():
    """Rule 0 must stay narrow: the whole site is served over Funnel, so a
    visitor loading a normal page carries this header on every request.
    """
    assert await get("/api/v1/projects", forwarded_for=VISITOR, funnel=FUNNEL_ON) == 200


async def test_admin_over_tailscale_carries_no_funnel_header_and_still_works():
    """The complement: admin traffic reaches Caddy's :8443 block over the
    tailnet, never through Funnel, so the header is absent and the request is
    judged by the entry marker alone.
    """
    status = await get(
        "/api/v1/admin/analytics",
        forwarded_for=VISITOR,
        entry=SECRET_ENTRY,
        admin_entry=SECRET_ENTRY,
    )
    assert status == 200
