"""Tests for real-client-IP resolution behind the reverse proxy.

These guard the invariant `auth_service.check_rate_limit` depends on: two
different visitors must produce two different `ip_hash` values. Before the
proxy-header fix they all collapsed to Caddy's address, silently turning
per-IP login throttling into a global one (see app/middleware/proxy.py).
"""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.main import app as real_app
from app.middleware.proxy import client_ip
from app.services import auth_service

TRUSTED_PROXY = "10.9.0.7"
UNTRUSTED_PEER = "203.0.113.9"
VISITOR_A = "198.51.100.7"
VISITOR_B = "198.51.100.42"


def build_probe_app(trusted_hosts: list[str]) -> FastAPI:
    """A stand-in for the real app, wired exactly as `app.main` wires it, with
    one route that reports what the app believes the client IP to be.

    Used instead of the real app so these tests stay free of a database: the
    routes that consume `client_ip()` both need one, but the resolution being
    tested happens before any of them run.
    """
    probe = FastAPI()

    @probe.get("/probe")
    async def probe_route(request: Request) -> dict:
        resolved = client_ip(request)
        return {"ip": resolved, "ip_hash": auth_service.hash_ip(resolved)}

    probe.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)
    return probe


async def get_probe(
    trusted_hosts: list[str],
    peer: str,
    forwarded_for: str | None = None,
) -> dict:
    transport = ASGITransport(app=build_probe_app(trusted_hosts), client=(peer, 0))
    headers = {"x-forwarded-for": forwarded_for} if forwarded_for is not None else {}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_forwarded_header_from_untrusted_peer_is_ignored():
    """The whole point of the trust list: a direct client cannot claim to be
    someone else just by sending the header itself.
    """
    body = await get_probe([TRUSTED_PROXY], peer=UNTRUSTED_PEER, forwarded_for=VISITOR_A)
    assert body["ip"] == UNTRUSTED_PEER


async def test_forwarded_header_from_trusted_proxy_is_used():
    body = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY, forwarded_for=VISITOR_A)
    assert body["ip"] == VISITOR_A


async def test_distinct_visitors_behind_proxy_hash_differently():
    """M16's stated verification, and the regression this fix exists to
    prevent: if these two hashes were equal, one visitor's failed logins
    would consume every other visitor's rate-limit allowance.
    """
    first = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY, forwarded_for=VISITOR_A)
    second = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY, forwarded_for=VISITOR_B)

    assert first["ip"] != second["ip"]
    assert first["ip_hash"] != second["ip_hash"]


async def test_same_visitor_hashes_consistently():
    """The complement of the test above — rate limiting also breaks if a
    single attacker's attempts scatter across different buckets.
    """
    first = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY, forwarded_for=VISITOR_A)
    second = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY, forwarded_for=VISITOR_A)

    assert first["ip_hash"] == second["ip_hash"]


async def test_trusted_proxy_accepts_cidr_range():
    """Production trusts the Caddy container's Docker network rather than a
    fixed address, since container IPs are assigned dynamically.
    """
    body = await get_probe(["10.9.0.0/16"], peer=TRUSTED_PROXY, forwarded_for=VISITOR_A)
    assert body["ip"] == VISITOR_A


async def test_forwarded_chain_resolves_to_last_untrusted_hop():
    """With several proxies in front, the real visitor is the last entry that
    isn't one of ours — not simply the first entry, which a client can forge
    by sending its own `X-Forwarded-For` that our proxy then appends to.
    """
    body = await get_probe(
        [TRUSTED_PROXY, "10.9.0.8"],
        peer=TRUSTED_PROXY,
        forwarded_for=f"{VISITOR_A}, 10.9.0.8",
    )
    assert body["ip"] == VISITOR_A


async def test_spoofed_forwarded_prefix_does_not_become_client():
    """A client sending its own forged `X-Forwarded-For` gets that value
    prepended, not honoured: its real address is still the last untrusted hop.
    """
    body = await get_probe(
        [TRUSTED_PROXY],
        peer=TRUSTED_PROXY,
        forwarded_for=f"1.2.3.4, {VISITOR_A}",
    )
    assert body["ip"] == VISITOR_A


async def test_missing_forwarded_header_falls_back_to_peer():
    body = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY)
    assert body["ip"] == TRUSTED_PROXY


async def test_empty_forwarded_header_falls_back_to_peer():
    """Caddy's public block sets `X-Forwarded-For` from `CF-Connecting-IP`
    (infrastructure/caddy/Caddyfile). A request that reaches Caddy without
    that header — only our own containers can produce one — therefore arrives
    here with an *empty* forwarded header rather than none at all. It must
    fail closed to the peer address, not to an empty client IP.
    """
    body = await get_probe([TRUSTED_PROXY], peer=TRUSTED_PROXY, forwarded_for="")
    assert body["ip"] == TRUSTED_PROXY
    assert body["ip_hash"] == auth_service.hash_ip(TRUSTED_PROXY)


@pytest.mark.parametrize("middleware_cls", [ProxyHeadersMiddleware])
def test_real_app_installs_proxy_headers_middleware(middleware_cls):
    """Guards the wiring itself: without this middleware on the real app, every
    test above still passes while production silently reverts to hashing
    Caddy's address for every visitor.
    """
    assert any(m.cls is middleware_cls for m in real_app.user_middleware)
