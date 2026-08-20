import enum

from pydantic import BaseModel

from app.models.analytics import AnalyticsEventType
from app.models.project import Locale


class Granularity(str, enum.Enum):
    day = "day"
    week = "week"
    month = "month"


class AnalyticsEventCreate(BaseModel):
    event_type: AnalyticsEventType
    session_id: str
    project_slug: str | None = None
    locale: Locale | None = None
    metadata: dict | None = None


class AnalyticsEventResponse(BaseModel):
    status: str


class AnalyticsSummary(BaseModel):
    total_page_views: int
    unique_sessions: int
    total_project_views: int
    github_clicks: int
    cv_downloads: int
    contact_clicks: int
    language_distribution: dict[str, int]


class TimeseriesPoint(BaseModel):
    date: str
    page_views: int
    unique_sessions: int


class TopProjectOut(BaseModel):
    slug: str
    title: str
    views: int


class RecentEventOut(BaseModel):
    event_type: str
    project_slug: str | None
    timestamp: str


class AdminAnalyticsResponse(BaseModel):
    summary: AnalyticsSummary
    timeseries: list[TimeseriesPoint]
    top_projects: list[TopProjectOut]
    recent_events: list[RecentEventOut]
