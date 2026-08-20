/**
 * Renders the dashboard against a full analytics payload.
 *
 * The point is not to re-test the numbers — the backend suite does that — but
 * to catch the failure this page is most exposed to: the response grew from
 * four top-level keys to ten, and every new section reads nested fields
 * (`engagement.bounceRate`, `topPages[].path`, `deviceBreakdown[].deviceClass`)
 * with no runtime guard. A field the API mapper forgets to camel-case, or a
 * section rendered before its data exists, throws inside render and the whole
 * admin page goes blank — a failure that typecheck cannot see, because the
 * mapper's own types would be wrong in exactly the same way.
 *
 * It also pins the two empty states that only appear on a fresh deploy:
 * devices and traffic sources report only over the window where those columns
 * were being collected, so on the day they ship they are legitimately empty and
 * must say why rather than render a blank card.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminAnalytics } from "../../types";
import "../../i18n";

const { getAdminAnalytics } = vi.hoisted(() => ({ getAdminAnalytics: vi.fn() }));

vi.mock("../../services/api", () => ({
  getAdminAnalytics,
  logout: vi.fn().mockResolvedValue(undefined),
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
    ) {
      super(message);
    }
  },
}));

// recharts measures its container, and jsdom reports every element as 0x0 —
// ResponsiveContainer then renders nothing and the chart's marks never mount.
// Giving it a fixed size is what lets the charts render at all in this
// environment; without it this test would pass while proving nothing about them.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <actual.ResponsiveContainer width={640} height={240}>
        {children as React.ReactElement}
      </actual.ResponsiveContainer>
    ),
  };
});

import AdminDashboard from "./AdminDashboard";

const FULL: AdminAnalytics = {
  summary: {
    totalPageViews: 172,
    uniqueSessions: 15,
    totalProjectViews: 28,
    githubClicks: 1,
    cvDownloads: 6,
    contactClicks: 3,
    projectLinkClicks: 0,
    languageChanges: 18,
    totalEvents: 228,
    languageDistribution: { en: 11, es: 9 },
  },
  engagement: {
    bounceRate: 0.4,
    pagesPerSession: 11.47,
    avgEventsPerSession: 15.2,
    avgSessionDurationSeconds: 125,
    returningSessions: 1,
  },
  timeseries: [{ date: "2026-08-20", pageViews: 152, uniqueSessions: 13, uniqueVisitors: 11 }],
  topProjects: [{ slug: "pokebot", title: "PokeBot", views: 8 }],
  topPages: [{ path: "/projects", views: 28, uniqueSessions: 12 }],
  eventBreakdown: [
    { eventType: "page_view", count: 172 },
    { eventType: "project_link_click", count: 0 },
  ],
  deviceBreakdown: [{ deviceClass: "mobile", sessions: 4 }],
  referrers: [{ host: "direct", sessions: 9 }],
  hourlyActivity: Array.from({ length: 24 }, (_, hour) => ({ hour, events: hour })),
  recentEvents: [{ eventType: "page_view", projectSlug: null, timestamp: "2026-08-20T15:00:00Z" }],
};

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/admin/dashboard"]}>
      <AdminDashboard />
    </MemoryRouter>,
  );
}

describe("AdminDashboard", () => {
  beforeEach(() => {
    getAdminAnalytics.mockReset();
  });

  it("renders every section of a full analytics payload", async () => {
    getAdminAnalytics.mockResolvedValue(FULL);
    renderDashboard();

    await waitFor(() => expect(screen.getByText("Traffic")).toBeInTheDocument());

    // Counts that previously had no tile at all.
    expect(screen.getByText("Total Events")).toBeInTheDocument();
    expect(screen.getByText("228")).toBeInTheDocument();
    expect(screen.getByText("Language Switches")).toBeInTheDocument();
    expect(screen.getByText("Demo Link Clicks")).toBeInTheDocument();

    // Derived engagement figures, formatted rather than raw.
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("2m 05s")).toBeInTheDocument();

    // Dimensions that needed new collection or a new query.
    expect(screen.getByText("Top Pages")).toBeInTheDocument();
    expect(screen.getByText("Devices")).toBeInTheDocument();
    expect(screen.getByText("Traffic Sources")).toBeInTheDocument();
    expect(screen.getByText("Activity by Hour")).toBeInTheDocument();
    expect(screen.getByText("Direct / bookmark")).toBeInTheDocument();

    // A zero-count type is listed, not omitted — the distinction between
    // "nobody did this" and "the instrumentation is broken".
    expect(screen.getByText("project_link_click")).toBeInTheDocument();
  });

  it("explains the empty device and source cards instead of leaving them blank", async () => {
    getAdminAnalytics.mockResolvedValue({ ...FULL, deviceBreakdown: [], referrers: [] });
    renderDashboard();

    await waitFor(() => expect(screen.getByText("Devices")).toBeInTheDocument());

    expect(screen.getAllByText(/Nothing recorded yet/i)).toHaveLength(2);
  });

  it("no longer claims the numbers are demo data", async () => {
    getAdminAnalytics.mockResolvedValue(FULL);
    renderDashboard();

    await waitFor(() => expect(screen.getByText("Traffic")).toBeInTheDocument());

    expect(screen.queryByText(/demo data/i)).not.toBeInTheDocument();
    expect(screen.getByText(/no third-party trackers/i)).toBeInTheDocument();
  });
});
