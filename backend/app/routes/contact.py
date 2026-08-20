import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.middleware.proxy import client_ip
from app.schemas.contact import ContactMessageCreate, ContactMessageResponse
from app.services import contact_service, rate_limit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contact", tags=["contact"])

RATE_LIMIT_SCOPE = "contact"


@router.post("", response_model=ContactMessageResponse)
async def submit_contact_message(
    payload: ContactMessageCreate, request: Request
) -> ContactMessageResponse:
    """Relay a contact-form submission to the site owner. Nothing is stored.

    Unauthenticated and it sends real email, so it is rate limited on the
    client's IP — the one key a submitter cannot choose for themselves.
    """
    if not settings.contact_email_configured:
        # An honest 503 rather than a cheerful 200: the previous version of
        # this form discarded messages while telling the visitor nothing.
        raise HTTPException(status_code=503, detail="The contact form is currently unavailable.")

    ip = client_ip(request)

    retry_after = rate_limit_service.check(
        RATE_LIMIT_SCOPE,
        ip,
        rate_limit_service.CONTACT_BURST,
        rate_limit_service.CONTACT_HOURLY,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many messages sent. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if payload.website:
        # Honeypot tripped. Answer exactly as success would, so a bot gets no
        # signal to adapt, but send nothing. Counted against the rate limit so
        # a bot cannot probe repeatedly for free.
        rate_limit_service.record(RATE_LIMIT_SCOPE, ip)
        logger.info("contact submission rejected: honeypot")
        return ContactMessageResponse(status="sent")

    try:
        await contact_service.send_contact_message(payload.name, payload.email, payload.message)
    except ValueError:
        raise HTTPException(status_code=422, detail="The message could not be accepted.")
    except contact_service.ContactDeliveryError:
        # 502, not 200: the visitor needs to know it did not arrive so they can
        # use the direct email link instead.
        raise HTTPException(
            status_code=502,
            detail="The message could not be delivered. Please email directly instead.",
        )

    rate_limit_service.record(RATE_LIMIT_SCOPE, ip)
    return ContactMessageResponse(status="sent")
