import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin import AdminSession, AdminUser, LoginAttempt

BCRYPT_ROUNDS = 12  # architecture.md §8: "bcrypt with work factor 12"

SESSION_DURATION = timedelta(hours=24)
RATE_LIMIT_WINDOW = timedelta(minutes=15)
RATE_LIMIT_MAX_ATTEMPTS = 5
BACKOFF_CAP_SECONDS = 60


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_ip(ip: str) -> str:
    """Groups attempts by client IP without persisting the raw address, matching
    the privacy stance already used for analytics IP hashing (architecture.md §9).
    """
    return hashlib.sha256(f"{ip}:{settings.session_secret_key}".encode()).hexdigest()


async def check_rate_limit(db: AsyncSession, ip_hash: str) -> int | None:
    """Returns seconds the caller must wait before another attempt is allowed,
    or None if the attempt may proceed now. Combines a hard cap (5 failures per
    15-minute window) with exponential backoff since the last failure.
    """
    window_start = datetime.now(timezone.utc) - RATE_LIMIT_WINDOW
    recent_failures = (
        await db.execute(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.ip_hash == ip_hash,
                LoginAttempt.success.is_(False),
                LoginAttempt.created_at >= window_start,
            )
        )
    ).scalar_one()

    if recent_failures >= RATE_LIMIT_MAX_ATTEMPTS:
        return int(RATE_LIMIT_WINDOW.total_seconds())

    if recent_failures == 0:
        return None

    last_attempt = (
        await db.execute(
            select(LoginAttempt.created_at)
            .where(LoginAttempt.ip_hash == ip_hash, LoginAttempt.success.is_(False))
            .order_by(LoginAttempt.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if last_attempt is None:
        return None

    backoff = min(2**recent_failures, BACKOFF_CAP_SECONDS)
    elapsed = (datetime.now(timezone.utc) - last_attempt).total_seconds()
    remaining = backoff - elapsed
    return int(remaining) if remaining > 0 else None


async def record_login_attempt(db: AsyncSession, ip_hash: str, success: bool) -> None:
    db.add(LoginAttempt(ip_hash=ip_hash, success=success))
    await db.commit()


async def authenticate(db: AsyncSession, username: str, password: str) -> AdminUser | None:
    user = (await db.execute(select(AdminUser).where(AdminUser.username == username))).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


async def create_session(db: AsyncSession, user: AdminUser) -> tuple[str, datetime]:
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    db.add(AdminSession(session_id=session_id, user_id=user.id, expires_at=expires_at))
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    return session_id, expires_at


async def get_session_user(db: AsyncSession, session_id: str) -> AdminUser | None:
    session = (
        await db.execute(select(AdminSession).where(AdminSession.session_id == session_id))
    ).scalar_one_or_none()
    if session is None:
        return None

    if session.expires_at < datetime.now(timezone.utc):
        await db.delete(session)
        await db.commit()
        return None

    # Sliding expiration: an active session keeps renewing rather than hard-expiring
    # mid-use (architecture.md §8: "renewable on activity").
    session.expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    user = (await db.execute(select(AdminUser).where(AdminUser.id == session.user_id))).scalar_one_or_none()
    await db.commit()
    return user


async def delete_session(db: AsyncSession, session_id: str) -> None:
    session = (
        await db.execute(select(AdminSession).where(AdminSession.session_id == session_id))
    ).scalar_one_or_none()
    if session is not None:
        await db.delete(session)
        await db.commit()
