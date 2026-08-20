from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.admin import AdminUser
from app.services import auth_service

SESSION_COOKIE_NAME = "portfolio_session"


async def get_current_admin(request: Request, db: AsyncSession = Depends(get_db)) -> AdminUser:
    """FastAPI dependency protecting admin-only routes. Reads the opaque session
    cookie, resolves it against `admin_sessions`, and 401s on anything invalid —
    missing cookie, unknown session, or expired session.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await auth_service.get_session_user(db, session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return user
