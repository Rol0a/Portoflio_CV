from datetime import datetime

from pydantic import BaseModel


class ServiceCheck(BaseModel):
    status: str
    latency_ms: float | None = None


class TargetCheck(BaseModel):
    reachable: bool
    latency_ms: float | None = None


class NetworkHealthSampleOut(BaseModel):
    sampled_at: datetime
    services: dict[str, ServiceCheck]
    internet_targets: dict[str, TargetCheck]
    packet_loss_pct: float | None
    cpu_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    requests_count: int | None
    errors_count: int | None

    model_config = {"from_attributes": True}


class ActiveVisitorsOut(BaseModel):
    """M8 extension — see analytics_service.get_active_visitor_count.
    window_minutes travels with the count so the frontend never hardcodes a
    number that only the backend actually enforces.
    """

    count: int
    window_minutes: int


class NetworkHealthSamples(BaseModel):
    """NOC-only data — what network_health_service actually owns. Kept
    separate from NetworkHealthResponse so that service never needs to know
    about active_visitors, which comes from a different service entirely
    (see routes/admin.py's get_network_health, the only place these merge).
    """

    latest: NetworkHealthSampleOut | None
    history: list[NetworkHealthSampleOut]


class NetworkHealthResponse(BaseModel):
    latest: NetworkHealthSampleOut | None
    history: list[NetworkHealthSampleOut]
    active_visitors: ActiveVisitorsOut
