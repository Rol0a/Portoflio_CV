from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.proxy import client_ip
from app.schemas.analytics import AnalyticsEventCreate, AnalyticsEventResponse
from app.services import analytics_service, rate_limit_service

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

RATE_LIMIT_SCOPE = "analytics"


@router.post("/events", response_model=AnalyticsEventResponse)
async def record_event(
    payload: AnalyticsEventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AnalyticsEventResponse:
    ip = client_ip(request)

    # The limit inside analytics_service keys on payload.session_id, which the
    # client chooses — rotating it per request bypasses the cap entirely and
    # writes unbounded rows (M16). This backstop keys on the IP instead, which
    # the client cannot pick. Both apply: the session limit shapes one
    # visitor's behaviour, this one bounds a flood.
    if rate_limit_service.check(RATE_LIMIT_SCOPE, ip, rate_limit_service.ANALYTICS_PER_IP):
        # A beacon has no useful way to react to a 4xx, so answer 200 with a
        # status the caller can ignore — matching how the service reports its
        # own rate limiting.
        return AnalyticsEventResponse(status="rate_limited")
    rate_limit_service.record(RATE_LIMIT_SCOPE, ip)

    user_agent = request.headers.get("user-agent")
    status = await analytics_service.record_event(db, payload, ip, user_agent)
    return AnalyticsEventResponse(status=status)
