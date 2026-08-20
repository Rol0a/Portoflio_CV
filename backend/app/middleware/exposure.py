"""Second, independent enforcement of which surfaces are reachable from where.

`infrastructure/caddy/Caddyfile` already refuses `/internal/*`,
`/api/v1/admin/*`, `/api/v1/auth/*` and `/admin*` on the public site block,
and `docs/security.md` §3 explains why. That is the primary control and it
works — but it is the *only* control, and it lives entirely in one file that
this application neither owns nor validates at runtime. Three ordinary events
silently remove it:

- the Caddyfile is edited and a `handle` block is dropped or reordered;
- the tunnel's ingress rule is repointed straight at `backend:8000`,
  bypassing Caddy altogether (a plausible "let me rule out the proxy"
  debugging step, and one that would put the admin API on the internet);
- the stack is brought up without the `caddy` service at all.

In every one of those cases the backend today would happily serve
`/internal/metrics` and the admin API to whoever asked. This middleware is
the second lock: the app enforces its own exposure rules, so both layers have
to fail together, not just one.

The rules are deliberately of different kinds, so that one mistake cannot
disable all of them. Rule 0 is the outermost and the only one whose evidence
this project does not produce itself:

0. **Anything Tailscale marks as a public Funnel request is refused outright
   on every non-public surface.** `Tailscale-Funnel-Request` is set by
   Tailscale on ingress and overwrites any client-supplied value, so a visitor
   can neither forge it nor strip it. Because it originates outside this
   codebase, it still holds when the Caddyfile is wrong, absent, or bypassed —
   precisely the moments the other two signals stop being trustworthy.

1. **`/internal/*` is for unproxied, in-network callers only.** The `noc`
   service reaches it directly over the Docker network as
   `http://backend:8000/internal/metrics`, so a legitimate request carries no
   `X-Forwarded-For` at all, while anything that passed through *any* proxy
   has one. This needs no shared secret and no knowledge of Caddy's address —
   it keys on a structural property of the only supported call path.

2. **Admin and auth surfaces require proof of admin entry, whenever the
   request was proxied at all.** Caddy's Tailscale-bound admin block stamps
   `X-Portfolio-Entry` with the expected value; its public block stamps
   `public`. Both *set* the header rather than appending, so a value supplied
   by a visitor is overwritten and cannot survive the public path.

   The check is "proxied and not marked admin → refuse", not "marked public →
   refuse", specifically so it also covers the bypass case: a request arriving
   from a repointed tunnel has an `X-Forwarded-For` (cloudflared adds one) and
   no entry marker at all, and is refused on those grounds. An *unproxied*
   request has neither header and is allowed — that is dev, the test client,
   and direct in-network calls, none of which can originate from the internet
   given nothing in `docker-compose.yml` publishes the backend's port.

   `ADMIN_ENTRY_TOKEN` upgrades the marker from a known constant to a shared
   secret. Without it the expected value is the literal `admin`, which an
   attacker who has *already* bypassed Caddy could guess and send; with it,
   forging the marker requires the secret. The fallback exists so a fresh
   checkout works unconfigured, and it announces itself at startup rather than
   degrading silently — the same pattern `noc/monitor.py` uses for its
   database credential.

Both rules answer 404, matching Caddy, so neither confirms to an outside
prober that the path exists at all.
"""

import ipaddress
import logging

logger = logging.getLogger(__name__)

# Set by Caddy on every proxied request; see infrastructure/caddy/Caddyfile.
ENTRY_HEADER = b"x-portfolio-entry"

# Set by Tailscale itself on every request arriving through Funnel, i.e. from
# the public internet rather than the tailnet. Verified empirically: a client
# forging `Tailscale-Funnel-Request: ?0` through the public ingress had it
# overwritten with `?1` before reaching this host, so its presence cannot be
# faked *away* by a visitor trying to look like tailnet traffic.
#
# This is the strongest of the three signals here because it is the only one
# set outside this project — it holds even if the Caddyfile is wrong, absent,
# or bypassed, which is exactly when the other two stop being trustworthy.
FUNNEL_HEADER = b"tailscale-funnel-request"

# The marker used when ADMIN_ENTRY_TOKEN is unset. A known constant, so it
# only defends against the Caddy-layer regressions above, not against an
# attacker who already reaches the backend directly and knows this file.
DEFAULT_ADMIN_ENTRY = "admin"

# Surfaces that must never be served to a request proxied from anywhere but
# the admin site block. `/api/v1/admin` and `/admin` are written without a
# trailing slash so that `/admin`, `/admin/dashboard`, and
# `/api/v1/admin/analytics` are all covered.
ADMIN_PREFIXES = ("/api/v1/admin", "/api/v1/auth", "/admin")

# Reachable only by a direct, in-network caller — never through a proxy.
INTERNAL_PREFIX = "/internal/"

_NOT_FOUND_BODY = b'{"detail":"Not Found"}'


def _is_private_peer(client: tuple | None) -> bool:
    """True when the immediate peer is on a private/loopback network.

    A container on `portfolio-net` (172.20.0.0/16) and a test client on
    loopback both qualify; anything routable from the internet does not. An
    unparseable or absent peer is treated as untrusted.
    """
    if not client:
        return False
    try:
        address = ipaddress.ip_address(client[0])
    except ValueError:
        return False
    return address.is_private or address.is_loopback


class ExposureGuardMiddleware:
    """Raw ASGI middleware, matching MetricsMiddleware — there is no response
    body to inspect here, so BaseHTTPMiddleware's buffering would buy nothing.
    """

    def __init__(self, app, admin_entry: str | None = None):
        self.app = app
        self.expected_entry = (admin_entry or DEFAULT_ADMIN_ENTRY).encode()
        self.entry_is_secret = bool(admin_entry)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        forwarded_for = None
        entry = None
        via_funnel = False
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                forwarded_for = value
            elif name == ENTRY_HEADER:
                entry = value
            elif name == FUNNEL_HEADER:
                via_funnel = True

        denial = None

        if via_funnel and path.startswith((INTERNAL_PREFIX,) + ADMIN_PREFIXES):
            # Checked before anything else: Tailscale says this came from the
            # public internet, and no admin or internal surface is ever served
            # to the public internet. Nothing downstream — not a valid entry
            # marker, not a private-looking peer — can override that.
            denial = "public Funnel request to a non-public surface"

        elif path.startswith(INTERNAL_PREFIX):
            # See rule 1. Read from the original header, not scope["client"]:
            # ProxyHeadersMiddleware sits outside this one and rewrites the
            # peer to the forwarded visitor, which would make a proxied
            # request look local.
            if forwarded_for is not None:
                denial = "internal path reached through a proxy"
            elif not _is_private_peer(scope.get("client")):
                denial = "internal path reached from a non-private peer"

        elif path.startswith(ADMIN_PREFIXES) and forwarded_for is not None:
            # See rule 2. Only proxied requests are judged: an unproxied one
            # cannot have come from the internet on this deployment.
            if entry != self.expected_entry:
                denial = "admin surface reached from outside the admin entry point"

        if denial is not None:
            # WARNING, not DEBUG: arriving here means the Caddy layer did not
            # do its job. This is the alarm that the primary control has
            # regressed, so it has to be loud enough to notice rather than a
            # silent 404 indistinguishable from a typo'd URL.
            logger.warning("exposure guard refused %s: %s", path, denial)
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(_NOT_FOUND_BODY)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": _NOT_FOUND_BODY})
            return

        await self.app(scope, receive, send)
