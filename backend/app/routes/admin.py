from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.security import get_current_admin
from app.models.admin import AdminUser
from app.schemas.analytics import AdminAnalyticsResponse, Granularity
from app.schemas.network_health import NetworkHealthResponse
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
    """Samples come from the standalone `noc` service, not this request —
    this just reads what it already wrote to `network_health_samples`."""
    return await network_health_service.get_network_health(db)
