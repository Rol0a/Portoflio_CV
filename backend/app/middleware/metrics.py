import time
from typing import ClassVar


class RequestMetrics:
    """In-process counters, reset on every backend restart/deploy — deltas
    between NOC polls are what get persisted (see network_health_service),
    so a reset just shows up as one low-count sample, not a broken history.
    """

    requests_total: ClassVar[int] = 0
    errors_total: ClassVar[int] = 0
    started_at: ClassVar[float] = time.time()


class MetricsMiddleware:
    """Raw ASGI middleware (not BaseHTTPMiddleware — avoids buffering the
    response body just to read a status code) counting total requests and
    5xx responses. Backs GET /internal/metrics, which the standalone `noc`
    service polls over the Docker network — Caddy never proxies `/internal/*`
    from the public internet, so this stays unreachable from outside the
    compose network without needing its own auth. See docs/security.md.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_holder: dict[str, int] = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        RequestMetrics.requests_total += 1
        if status_holder.get("status", 200) >= 500:
            RequestMetrics.errors_total += 1
