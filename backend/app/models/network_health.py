from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NetworkHealthSample(Base):
    """One poll from the standalone `noc` service (see /noc at repo root).

    `services` / `internet_targets` are JSONB (keys vary: which containers
    exist, which external targets are configured) — same "structured but
    variable-shaped" rationale as AnalyticsEvent.metadata. Everything that's
    always present and gets charted directly is a plain typed column.
    """

    __tablename__ = "network_health_samples"
    __table_args__ = (Index("idx_nhs_sampled_at", "sampled_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # {"postgres": {"status": "up", "latency_ms": 1.8}, "backend": {...}, "caddy": {...}}
    services: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # {"1.1.1.1": {"reachable": true, "latency_ms": 11.4}, "8.8.8.8": {...}, "9.9.9.9": {...}}
    internet_targets: Mapped[dict] = mapped_column(JSONB, nullable=False)

    packet_loss_pct: Mapped[float | None] = mapped_column(Float)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_percent: Mapped[float | None] = mapped_column(Float)
    disk_percent: Mapped[float | None] = mapped_column(Float)

    # Requests/errors served by the backend since the previous sample (a
    # rate, not a running total) — see the backend's /internal/metrics.
    requests_count: Mapped[int | None] = mapped_column(Integer)
    errors_count: Mapped[int | None] = mapped_column(Integer)
