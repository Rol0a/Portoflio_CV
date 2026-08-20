from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.security import get_current_admin
from app.models.admin import AdminUser
from app.schemas.analytics import AdminAnalyticsResponse, Granularity
from app.schemas.network_health import ActiveVisitorsOut, NetworkHealthResponse
from app.services import analytics_service, network_health_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/analytics", response_model=AdminAnalyticsResponse)
async def get_admin_analytics(
    days: int = Query(default=30, ge=1, le=365),
    granularity: Granularity = Query(default=Granularity.day),
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> AdminAnalyticsResponse:
    return await analytics_service.get_admin_analytics(db, days=days, granularity=granularity)


@router.get("/network-health", response_model=NetworkHealthResponse)
async def get_network_health(
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> NetworkHealthResponse:
    """Two independent data sources, merged here rather than in either
    service, so each stays about only its own domain:

    - `network_health_service` reads samples the standalone `noc` service
      already wrote to `network_health_samples` — as fresh as its last poll
      (~30s), not this request.
    - `analytics_service.get_active_visitor_count` queries `analytics_events`
      directly, computed fresh on every call — this is the "live" half (M8
      extension): unlike the NOC data, it reflects the instant this endpoint
      is hit, not a periodic sample.
    """
    health = await network_health_service.get_network_health(db)
    active_count = await analytics_service.get_active_visitor_count(db)
    return NetworkHealthResponse(
        latest=health.latest,
        history=health.history,
        active_visitors=ActiveVisitorsOut(
            count=active_count,
            window_minutes=analytics_service.ACTIVE_VISITOR_WINDOW_MINUTES,
        ),
    )
