from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.certification import Certification, CertificationTranslation
from app.models.project import Locale
from app.schemas.certification import CertificationOut


async def list_certifications(
    db: AsyncSession, locale: Locale, featured: bool | None = None
) -> list[CertificationOut]:
    stmt = (
        select(Certification)
        .join(Certification.translations)
        .where(CertificationTranslation.locale == locale)
        .options(selectinload(Certification.translations))
        .order_by(Certification.sort_order)
    )
    if featured is not None:
        stmt = stmt.where(Certification.featured == featured)

    result = await db.execute(stmt)
    certifications = result.scalars().unique().all()

    items = []
    for cert in certifications:
        translation = next(t for t in cert.translations if t.locale == locale)
        items.append(
            CertificationOut(
                id=str(cert.id),
                slug=cert.slug,
                issuer=cert.issuer,
                issue_date=cert.issue_date,
                expiry_date=cert.expiry_date,
                credential_url=cert.credential_url,
                badge_image_url=cert.badge_image_url,
                featured=cert.featured,
                title=translation.title,
                description=translation.description,
            )
        )
    return items
