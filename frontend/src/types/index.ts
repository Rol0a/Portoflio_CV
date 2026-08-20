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

export interface ProjectListItem {
  id: string;
  slug: string;
  category: ProjectCategory;
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
  | "electronics"
  | "automation"
  | "web_dev"
  | "ml_data"
  | "cybersecurity"
  | "linux_devops"
  | "engineering_tools";

export interface Skill {
  name: string;
  proficiency: number | null;
}

export interface SkillGroup {
  category: SkillCategory;
  skills: Skill[];
}

export interface AnalyticsSummary {
  totalPageViews: number;
  uniqueSessions: number;
  totalProjectViews: number;
  githubClicks: number;
  cvDownloads: number;
  contactClicks: number;
  languageDistribution: Record<string, number>;
}

export interface TimeseriesPoint {
  date: string;
  pageViews: number;
  uniqueSessions: number;
}

export interface TopProject {
  slug: string;
  title: string;
  views: number;
}

export interface RecentEvent {
  eventType: string;
  projectSlug: string | null;
  timestamp: string;
}

export interface AdminAnalytics {
  summary: AnalyticsSummary;
  timeseries: TimeseriesPoint[];
  topProjects: TopProject[];
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

export interface NetworkHealth {
  latest: NetworkHealthSample | null;
  history: NetworkHealthSample[];
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
