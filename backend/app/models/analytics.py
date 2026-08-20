import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.project import Locale


class AnalyticsEventType(str, enum.Enum):
    page_view = "page_view"
    project_view = "project_view"
    project_link_click = "project_link_click"
    github_click = "github_click"
    cv_download = "cv_download"
    contact_click = "contact_click"
    language_change = "language_change"


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("idx_analytics_event_type", "event_type"),
        Index("idx_analytics_created_at", "created_at"),
        Index("idx_analytics_project_id", "project_id"),
        Index("idx_analytics_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[AnalyticsEventType] = mapped_column(
        Enum(AnalyticsEventType, name="analytics_event_type"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    project_slug: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[Locale | None] = mapped_column(Enum(Locale, name="locale_type"))
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    user_agent_hash: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
