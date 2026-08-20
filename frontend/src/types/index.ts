export type ProjectCategory =
  | "featured"
  | "software"
  | "embedded"
  | "electronics"
  | "robotics"
  | "ml_data"
  | "cybersecurity"
  | "devops_infra"
  | "academic_research";

/** Mirrors backend `ProjectStatus` — see backend/app/models/project.py. */
export type ProjectStatus = "complete" | "in_development";

export interface ProjectListItem {
  id: string;
  slug: string;
  category: ProjectCategory;
  status: ProjectStatus;
  githubUrl: string | null;
  demoUrl: string | null;
  featured: boolean;
  title: string;
  shortDesc: string;
  technologies: string[];
  heroImageUrl: string | null;
}

export interface ProjectTechnology {
  name: string;
  category: string;
}

export interface ProjectImage {
  url: string;
  altText: string | null;
  isHero: boolean;
}

export interface ProjectDetail {
  id: string;
  slug: string;
  category: ProjectCategory;
  status: ProjectStatus;
  githubUrl: string | null;
  demoUrl: string | null;
  featured: boolean;
  title: string;
  shortDesc: string;
  overview: string | null;
  problem: string | null;
  requirements: string | null;
  architecture: string | null;
  implementation: string | null;
  decisions: string | null;
  challenges: string | null;
  testingDesc: string | null;
  results: string | null;
  lessons: string | null;
  technologies: ProjectTechnology[];
  images: ProjectImage[];
}

export type SkillCategory =
  | "programming"
  | "embedded_systems"
  | "hardware_design"
  | "robotics"
  | "networks"
  | "web_backend"
  | "linux_devops"
  | "data_ml";

export interface Skill {
  name: string;
}

export interface SkillGroup {
  category: SkillCategory;
  skills: Skill[];
}

/** Featured is a curated cross-section, not a ninth category — see the backend
 *  `SkillCategory` docstring for why it isn't an enum value. */
export interface Skills {
  featured: Skill[];
  groups: SkillGroup[];
}

export interface AnalyticsSummary {
  totalPageViews: number;
  uniqueSessions: number;
  totalProjectViews: number;
  githubClicks: number;
  cvDownloads: number;
  contactClicks: number;
  projectLinkClicks: number;
  languageChanges: number;
  totalEvents: number;
  languageDistribution: Record<string, number>;
}

export interface EngagementSummary {
  /** 0-1, not a percentage — the view formats it. */
  bounceRate: number;
  pagesPerSession: number;
  avgEventsPerSession: number;
  avgSessionDurationSeconds: number;
  returningSessions: number;
}

export interface TimeseriesPoint {
  date: string;
  pageViews: number;
  uniqueSessions: number;
  uniqueVisitors: number;
}

export interface TopProject {
  slug: string;
  title: string;
  views: number;
}

export interface TopPage {
  path: string;
  views: number;
  uniqueSessions: number;
}

export interface EventCount {
  eventType: string;
  count: number;
}

export interface DeviceCount {
  deviceClass: string;
  sessions: number;
}

export interface ReferrerCount {
  host: string;
  sessions: number;
}

export interface HourlyPoint {
  hour: number;
  events: number;
}

export interface RecentEvent {
  eventType: string;
  projectSlug: string | null;
  timestamp: string;
}

export interface AdminAnalytics {
  summary: AnalyticsSummary;
  engagement: EngagementSummary;
  timeseries: TimeseriesPoint[];
  topProjects: TopProject[];
  topPages: TopPage[];
  eventBreakdown: EventCount[];
  deviceBreakdown: DeviceCount[];
  referrers: ReferrerCount[];
  hourlyActivity: HourlyPoint[];
  recentEvents: RecentEvent[];
}

export interface ServiceCheck {
  status: string;
  latencyMs: number | null;
}

export interface TargetCheck {
  reachable: boolean;
  latencyMs: number | null;
}

export interface NetworkHealthSample {
  sampledAt: string;
  services: Record<string, ServiceCheck>;
  internetTargets: Record<string, TargetCheck>;
  packetLossPct: number | null;
  cpuPercent: number | null;
  memoryPercent: number | null;
  diskPercent: number | null;
  requestsCount: number | null;
  errorsCount: number | null;
}

export interface ActiveVisitors {
  count: number;
  windowMinutes: number;
}

export interface NetworkHealth {
  latest: NetworkHealthSample | null;
  history: NetworkHealthSample[];
  activeVisitors: ActiveVisitors;
}

export type Granularity = "day" | "week" | "month";

export type AnalyticsEventType =
  | "page_view"
  | "project_view"
  | "project_link_click"
  | "github_click"
  | "cv_download"
  | "contact_click"
  | "language_change";

export interface Certification {
  id: string;
  slug: string;
  issuer: string;
  issueDate: string;
  expiryDate: string | null;
  credentialUrl: string | null;
  badgeImageUrl: string | null;
  featured: boolean;
  title: string;
  description: string | null;
}
