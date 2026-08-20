from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.proxy import client_ip
from app.middleware.security import SESSION_COOKIE_NAME
from app.schemas.auth import AuthStatusResponse, LoginRequest
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=AuthStatusResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthStatusResponse:
    ip_hash = auth_service.hash_ip(client_ip(request))

    retry_after = await auth_service.check_rate_limit(db, ip_hash)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = await auth_service.authenticate(db, payload.username, payload.password)
    if user is None:
        await auth_service.record_login_attempt(db, ip_hash, success=False)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    await auth_service.record_login_attempt(db, ip_hash, success=True)
    session_id, expires_at = await auth_service.create_session(db, user)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
        max_age=int(auth_service.SESSION_DURATION.total_seconds()),
    )
    return AuthStatusResponse(status="authenticated")


@router.post("/logout", response_model=AuthStatusResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthStatusResponse:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is not None:
        await auth_service.delete_session(db, session_id)

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return AuthStatusResponse(status="logged_out")
