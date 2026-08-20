import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import settings
from app.database import async_session_factory, engine
from app.middleware.exposure import ExposureGuardMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.routes import (
    admin,
    analytics,
    auth,
    certifications,
    contact,
    internal,
    projects,
    skills,
)
from app.services import retention_service

# Without a handler on the root logger, application-level INFO is discarded —
# uvicorn only configures its own `uvicorn.*` loggers, which don't propagate.
# That silently swallowed the retention sweep's "deleted N rows" line, i.e. the
# only evidence the privacy commitment in architecture.md §9 is being kept.
# (WARNING and above did still surface, via logging's last-resort handler.)
# basicConfig is a no-op if something has already configured logging.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     [%(name)s] %(message)s")

logger = logging.getLogger(__name__)


async def _retention_loop() -> None:
    """Enforce the retention windows on a timer (M16).

    Sweeps once at startup rather than waiting a full interval, so a stack that
    is restarted more often than the interval still purges — otherwise a daily
    sweep on a server rebooted every morning would never run at all.
    """
    interval = settings.retention_purge_interval_hours * 3600
    while True:
        try:
            async with async_session_factory() as db:
                await retention_service.purge_all(db)
        except Exception:
            # Never let a purge failure take the API down with it; the next
            # tick retries, and the traceback is logged for diagnosis.
            logger.exception("retention purge failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if settings.retention_purge_enabled:
        task = asyncio.create_task(_retention_loop())
    else:
        logger.warning(
            "retention purge is DISABLED — analytics_events, login_attempts and "
            "admin_sessions will grow without bound (architecture.md §9)"
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()


app = FastAPI(title="Portfolio API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Inside MetricsMiddleware (added below), so a refusal still increments the
# request counter the NOC dashboard watches — a burst of guard denials is
# exactly the kind of thing that should be visible as traffic, not swallowed.
# See app/middleware/exposure.py for why the backend enforces this at all when
# the Caddyfile already does.
app.add_middleware(ExposureGuardMiddleware, admin_entry=settings.admin_entry_token or None)
app.add_middleware(MetricsMiddleware)

# Added last, so it sits outermost: every other middleware and route below it
# then reads an already-corrected client IP. See app/middleware/proxy.py for
# why this is wired here rather than via uvicorn's --proxy-headers flag.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)

if not settings.admin_entry_token:
    logger.warning(
        "ADMIN_ENTRY_TOKEN is unset — the exposure guard falls back to the literal "
        "marker 'admin' (app/middleware/exposure.py). That still catches a Caddy "
        "misconfiguration, but not an attacker who already reaches this backend "
        "directly. Set it in .env: openssl rand -hex 32"
    )

if "*" in settings.trusted_proxies:
    logger.warning(
        "TRUSTED_PROXY_IPS is '*' — any client can spoof its IP via X-Forwarded-For, "
        "which defeats login rate limiting and unique-visitor analytics. "
        "Set it to the reverse proxy's address or network instead."
    )

app.include_router(projects.router)
app.include_router(skills.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(certifications.router)
app.include_router(contact.router)
app.include_router(internal.router)


@app.get("/api/v1/health")
async def health() -> dict:
    db_status = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"

    return {
        "status": "healthy",
        "database": db_status,
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
