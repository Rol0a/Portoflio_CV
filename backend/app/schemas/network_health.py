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


class NetworkHealthResponse(BaseModel):
    latest: NetworkHealthSampleOut | None
    history: list[NetworkHealthSampleOut]
