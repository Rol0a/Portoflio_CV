import type {
  AdminAnalytics,
  AnalyticsEventType,
  Certification,
  Granularity,
  NetworkHealth,
  NetworkHealthSample,
  ProjectDetail,
  ProjectListItem,
  SkillGroup,
  Skills,
} from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfterSeconds?: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const retryAfterHeader = response.headers.get("Retry-After");
    throw new ApiError(
      `Request to ${path} failed with ${response.status}`,
      response.status,
      retryAfterHeader ? Number(retryAfterHeader) : undefined,
    );
  }
  return response.json() as Promise<T>;
}

interface ProjectListItemResponse {
  id: string;
  slug: string;
  category: ProjectListItem["category"];
  status: ProjectListItem["status"];
  github_url: string | null;
  demo_url: string | null;
  featured: boolean;
  title: string;
  short_desc: string;
  technologies: string[];
  hero_image_url: string | null;
}

interface ProjectDetailResponse {
  id: string;
  slug: string;
  category: ProjectDetail["category"];
  status: ProjectDetail["status"];
  github_url: string | null;
  demo_url: string | null;
  featured: boolean;
  title: string;
  short_desc: string;
  overview: string | null;
  problem: string | null;
  requirements: string | null;
  architecture: string | null;
  implementation: string | null;
  decisions: string | null;
  challenges: string | null;
  testing_desc: string | null;
  results: string | null;
  lessons: string | null;
  technologies: { name: string; category: string }[];
  images: { url: string; alt_text: string | null; is_hero: boolean }[];
}

interface SkillsResponse {
  featured: { name: string }[];
  categories: { category: SkillGroup["category"]; skills: { name: string }[] }[];
}

function mapProjectListItem(item: ProjectListItemResponse): ProjectListItem {
  return {
    id: item.id,
    slug: item.slug,
    category: item.category,
    status: item.status,
    githubUrl: item.github_url,
    demoUrl: item.demo_url,
    featured: item.featured,
    title: item.title,
    shortDesc: item.short_desc,
    technologies: item.technologies,
    heroImageUrl: item.hero_image_url,
  };
}

function mapProjectDetail(item: ProjectDetailResponse): ProjectDetail {
  return {
    id: item.id,
    slug: item.slug,
    category: item.category,
    status: item.status,
    githubUrl: item.github_url,
    demoUrl: item.demo_url,
    featured: item.featured,
    title: item.title,
    shortDesc: item.short_desc,
    overview: item.overview,
    problem: item.problem,
    requirements: item.requirements,
    architecture: item.architecture,
    implementation: item.implementation,
    decisions: item.decisions,
    challenges: item.challenges,
    testingDesc: item.testing_desc,
    results: item.results,
    lessons: item.lessons,
    technologies: item.technologies,
    images: item.images.map((image) => ({
      url: image.url,
      altText: image.alt_text,
      isHero: image.is_hero,
    })),
  };
}

export async function getProjects(
  locale: string,
  category?: string,
  featured?: boolean,
): Promise<ProjectListItem[]> {
  const params = new URLSearchParams({ locale });
  if (category) params.set("category", category);
  if (featured !== undefined) params.set("featured", String(featured));
  const data = await request<{ projects: ProjectListItemResponse[] }>(`/api/v1/projects?${params}`);
  return data.projects.map(mapProjectListItem);
}

export async function getProject(slug: string, locale: string): Promise<ProjectDetail | null> {
  try {
    const data = await request<ProjectDetailResponse>(
      `/api/v1/projects/${encodeURIComponent(slug)}?locale=${locale}`,
    );
    return mapProjectDetail(data);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getSkills(): Promise<Skills> {
  const data = await request<SkillsResponse>("/api/v1/skills");
  return {
    featured: data.featured,
    groups: data.categories.map((group) => ({
      category: group.category,
      skills: group.skills,
    })),
  };
}

interface CertificationResponse {
  id: string;
  slug: string;
  issuer: string;
  issue_date: string;
  expiry_date: string | null;
  credential_url: string | null;
  badge_image_url: string | null;
  featured: boolean;
  title: string;
  description: string | null;
}

export async function getCertifications(locale: string, featured?: boolean): Promise<Certification[]> {
  const params = new URLSearchParams({ locale });
  if (featured !== undefined) params.set("featured", String(featured));
  const data = await request<{ certifications: CertificationResponse[] }>(`/api/v1/certifications?${params}`);
  return data.certifications.map((item) => ({
    id: item.id,
    slug: item.slug,
    issuer: item.issuer,
    issueDate: item.issue_date,
    expiryDate: item.expiry_date,
    credentialUrl: item.credential_url,
    badgeImageUrl: item.badge_image_url,
    featured: item.featured,
    title: item.title,
    description: item.description,
  }));
}

export async function login(username: string, password: string): Promise<void> {
  await request<{ status: string }>("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  });
}

export async function logout(): Promise<void> {
  await request<{ status: string }>("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
  });
}

interface AdminAnalyticsResponse {
  summary: {
    total_page_views: number;
    unique_sessions: number;
    total_project_views: number;
    github_clicks: number;
    cv_downloads: number;
    contact_clicks: number;
    language_distribution: Record<string, number>;
  };
  timeseries: { date: string; page_views: number; unique_sessions: number }[];
  top_projects: { slug: string; title: string; views: number }[];
  recent_events: { event_type: string; project_slug: string | null; timestamp: string }[];
}

export async function getAdminAnalytics(days: number, granularity: Granularity): Promise<AdminAnalytics> {
  const data = await request<AdminAnalyticsResponse>(
    `/api/v1/admin/analytics?days=${days}&granularity=${granularity}`,
    { credentials: "include" },
  );

  return {
    summary: {
      totalPageViews: data.summary.total_page_views,
      uniqueSessions: data.summary.unique_sessions,
      totalProjectViews: data.summary.total_project_views,
      githubClicks: data.summary.github_clicks,
      cvDownloads: data.summary.cv_downloads,
      contactClicks: data.summary.contact_clicks,
      languageDistribution: data.summary.language_distribution,
    },
    timeseries: data.timeseries.map((point) => ({
      date: point.date,
      pageViews: point.page_views,
      uniqueSessions: point.unique_sessions,
    })),
    topProjects: data.top_projects,
    recentEvents: data.recent_events.map((event) => ({
      eventType: event.event_type,
      projectSlug: event.project_slug,
      timestamp: event.timestamp,
    })),
  };
}

interface TrackEventInput {
  eventType: AnalyticsEventType;
  sessionId: string;
  locale: string;
  projectSlug?: string;
  metadata?: Record<string, unknown>;
}

export async function postAnalyticsEvent(input: TrackEventInput): Promise<void> {
  await request<{ status: string }>("/api/v1/analytics/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: input.eventType,
      session_id: input.sessionId,
      project_slug: input.projectSlug,
      locale: input.locale,
      metadata: input.metadata,
    }),
  });
}

interface ServiceCheckResponse {
  status: string;
  latency_ms: number | null;
}

interface TargetCheckResponse {
  reachable: boolean;
  latency_ms: number | null;
}

interface NetworkHealthSampleResponse {
  sampled_at: string;
  services: Record<string, ServiceCheckResponse>;
  internet_targets: Record<string, TargetCheckResponse>;
  packet_loss_pct: number | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  requests_count: number | null;
  errors_count: number | null;
}

interface ActiveVisitorsResponse {
  count: number;
  window_minutes: number;
}

interface NetworkHealthResponse {
  latest: NetworkHealthSampleResponse | null;
  history: NetworkHealthSampleResponse[];
  active_visitors: ActiveVisitorsResponse;
}

function mapNetworkHealthSample(item: NetworkHealthSampleResponse): NetworkHealthSample {
  return {
    sampledAt: item.sampled_at,
    services: Object.fromEntries(
      Object.entries(item.services).map(([key, value]) => [key, { status: value.status, latencyMs: value.latency_ms }]),
    ),
    internetTargets: Object.fromEntries(
      Object.entries(item.internet_targets).map(([key, value]) => [
        key,
        { reachable: value.reachable, latencyMs: value.latency_ms },
      ]),
    ),
    packetLossPct: item.packet_loss_pct,
    cpuPercent: item.cpu_percent,
    memoryPercent: item.memory_percent,
    diskPercent: item.disk_percent,
    requestsCount: item.requests_count,
    errorsCount: item.errors_count,
  };
}

export async function getNetworkHealth(): Promise<NetworkHealth> {
  const data = await request<NetworkHealthResponse>("/api/v1/admin/network-health", { credentials: "include" });
  return {
    latest: data.latest ? mapNetworkHealthSample(data.latest) : null,
    history: data.history.map(mapNetworkHealthSample),
    activeVisitors: { count: data.active_visitors.count, windowMinutes: data.active_visitors.window_minutes },
  };
}

export interface ContactMessageInput {
  name: string;
  email: string;
  message: string;
  /** Honeypot — always empty for real visitors; see the backend's contact schema. */
  website?: string;
}

/**
 * Relay a contact-form submission. The destination address lives only in the
 * backend's configuration, never here — anything in this bundle is public.
 * Throws ApiError on 429 (rate limited), 502 (delivery failed) and 503 (form
 * not configured) so the UI can tell the visitor what actually happened
 * instead of claiming success.
 */
export async function postContactMessage(input: ContactMessageInput): Promise<void> {
  await request<{ status: string }>("/api/v1/contact", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      email: input.email,
      message: input.message,
      website: input.website ?? "",
    }),
  });
}
