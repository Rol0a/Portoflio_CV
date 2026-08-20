from datetime import date

from pydantic import BaseModel


class CertificationOut(BaseModel):
    id: str
    slug: str
    issuer: str
    issue_date: date
    expiry_date: date | None
    credential_url: str | None
    badge_image_url: str | None
    featured: bool
    title: str
    description: str | None


class CertificationsResponse(BaseModel):
    certifications: list[CertificationOut]
