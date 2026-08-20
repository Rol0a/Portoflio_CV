from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.network_health import NetworkHealthSample
from app.schemas.network_health import NetworkHealthResponse, NetworkHealthSampleOut

RETENTION_DAYS = 7
HISTORY_LIMIT = 120  # ~1 hour at the default 30s poll interval


async def get_network_health(db: AsyncSession) -> NetworkHealthResponse:
    stmt = select(NetworkHealthSample).order_by(NetworkHealthSample.sampled_at.desc()).limit(HISTORY_LIMIT)
    result = await db.execute(stmt)
    samples = list(result.scalars().all())

    history = [NetworkHealthSampleOut.model_validate(sample) for sample in reversed(samples)]
    latest = history[-1] if history else None

    return NetworkHealthResponse(latest=latest, history=history)


async def purge_old_samples(db: AsyncSession) -> None:
    """Mirrors the analytics retention policy (§9 of architecture.md) — the NOC
    service polls every few seconds to minutes, so this table grows fast and
    isn't worth keeping beyond a short debugging window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    await db.execute(delete(NetworkHealthSample).where(NetworkHealthSample.sampled_at < cutoff))
    await db.commit()
