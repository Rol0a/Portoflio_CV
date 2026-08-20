import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSession(Base):
    """Server-side session store backing the HttpOnly session cookie (architecture.md §8).

    Deliberately NOT a JWT: the cookie only carries `session_id`, an opaque random
    token. All session state (owner, expiry) lives here so a session can be revoked
    server-side (logout, or a future "sign out everywhere") without any client trust.
    """

    __tablename__ = "admin_sessions"

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LoginAttempt(Base):
    """One row per login attempt, keyed by hashed client IP. Backs rate limiting
    and exponential backoff (architecture.md §8) without requiring Redis or any
    other component beyond the Postgres instance the project already runs.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (Index("idx_login_attempts_ip_created", "ip_hash", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
