import time

from fastapi import APIRouter

from app.middleware.metrics import RequestMetrics

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/metrics")
async def get_metrics() -> dict:
    """Not admin-auth-protected — it's unauthenticated on purpose, but it's
    also never proxied by Caddy (see infrastructure/caddy/Caddyfile), so it's
    only reachable from inside the Docker network the `noc` service shares.
    Nothing here is sensitive (request counts only), but it still shouldn't
    be public — see docs/security.md's internal-surfaces principle.
    """
    return {
        "requests_total": RequestMetrics.requests_total,
        "errors_total": RequestMetrics.errors_total,
        "uptime_seconds": time.time() - RequestMetrics.started_at,
    }
