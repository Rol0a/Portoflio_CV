import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import "./i18n";

vi.mock("./services/api", () => ({
  getProjects: vi.fn().mockResolvedValue([
    {
      id: "1",
      slug: "sumobot",
      category: "robotics",
      githubUrl: null,
      demoUrl: null,
      featured: true,
      title: "SumoBot Competition Robot",
      shortDesc: "Autonomous sumo robot.",
      technologies: ["Arduino", "C++"],
    },
  ]),
  getProject: vi.fn().mockResolvedValue(null),
  getSkills: vi.fn().mockResolvedValue([]),
  getCertifications: vi.fn().mockResolvedValue([]),
  postAnalyticsEvent: vi.fn().mockResolvedValue(undefined),
}));

describe("App", () => {
  it("renders the home page with navigation", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /projects/i }).length).toBeGreaterThan(0);
  });

  it("renders the projects list at /projects", async () => {
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("SumoBot Competition Robot")).toBeInTheDocument();
  });

  it("renders NotFound for an unknown route", () => {
    render(
      <MemoryRouter initialEntries={["/does-not-exist"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: /not found|no encontrada/i })).toBeInTheDocument();
  });
});
