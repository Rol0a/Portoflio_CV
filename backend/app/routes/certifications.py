from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Locale
from app.schemas.certification import CertificationsResponse
from app.services import certification_service

router = APIRouter(prefix="/api/v1/certifications", tags=["certifications"])


@router.get("", response_model=CertificationsResponse)
async def get_certifications(
    locale: Locale = Query(default=Locale.en),
    featured: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> CertificationsResponse:
    certifications = await certification_service.list_certifications(db, locale=locale, featured=featured)
    return CertificationsResponse(certifications=certifications)
