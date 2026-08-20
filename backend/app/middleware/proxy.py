"""Real-client-IP resolution behind the reverse proxy.

In production the backend never sees a visitor directly: traffic arrives via
Cloudflare Tunnel → Caddy → this app (docs/security.md §2). Without this
middleware, `request.client.host` is *Caddy's* address for every request,
which quietly breaks two things that are supposed to be per-visitor:

- `analytics_service.hash_ip_daily` — every visitor hashes to the same value,
  so the "approximate unique visitors" count collapses to 1
  (docs/security.md §9).
- `auth_service.check_rate_limit` — far worse. Login throttling is keyed on
  `hash_ip(...)`, so a single shared value turns "5 failed attempts per 15
  minutes per IP" into *5 per 15 minutes globally*: one attacker locks the
  real admin out of their own dashboard, and every attacker shares one
  allowance.

Both are fixed at the source — correcting `scope["client"]` once, here, so
every downstream caller of `client_ip()` gets the true address.

**Why this is wired in code rather than via uvicorn's `--proxy-headers`
CLI flag:** the trust boundary is security-critical, so it belongs in
`config.py` with the rest of the security settings rather than split across
`backend/Dockerfile`'s CMD and `docker-compose.dev.yml`'s `command:`, where
an unrelated edit to either could silently drop it. Wiring it in the app
also makes it testable (see `tests/test_proxy_headers.py`) — a CLI flag is
not exercised by the test suite at all.

The parsing itself is uvicorn's own `ProxyHeadersMiddleware`, not a
reimplementation: it already handles CIDR ranges and walks the
`X-Forwarded-For` chain in reverse to find the first *untrusted* hop, which
is the part naive implementations get wrong.
"""

from fastapi import Request

CLIENT_IP_UNKNOWN = "unknown"


def client_ip(request: Request) -> str:
    """The requesting client's IP, or `"unknown"` if the server can't tell.

    Only trustworthy because `ProxyHeadersMiddleware` has already rewritten
    `scope["client"]` from `X-Forwarded-For` for requests arriving from a
    trusted proxy — see this module's docstring. Call this instead of reading
    `request.client` directly, so there is one place to audit.
    """
    return request.client.host if request.client else CLIENT_IP_UNKNOWN
