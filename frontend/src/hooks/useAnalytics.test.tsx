/**
 * Client-side analytics test bench — the counterpart to the backend's
 * tests/test_analytics_privacy.py.
 *
 * The backend bench proves nothing personal is *stored*. This one proves
 * nothing personal is *sent* in the first place, which is the stronger
 * property: data that never leaves the browser cannot leak from the server.
 *
 * The case that matters most is the Contact page. It asks the visitor for a
 * name, an email address and a message, and its submit handler fires a
 * `contact_click` analytics event. Nothing in the type signature stops those
 * field values from being attached to that event, so this file pins the
 * behaviour down: the event carries the fact that a submission happened, and
 * none of what was typed.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Contact from "../pages/Contact/Contact";
import { useAnalytics } from "./useAnalytics";
import { ApiError, postAnalyticsEvent, postContactMessage } from "../services/api";
import "../i18n";

vi.mock("../services/api", () => {
  // The real ApiError is needed as a constructor, because Contact's catch
  // branch does `error instanceof ApiError`. A factory returning only the
  // functions leaves it undefined, which throws inside the catch and makes
  // these tests pass while erroring — so it is stubbed faithfully here.
  class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
    ) {
      super(message);
    }
  }
  return {
    ApiError,
    postAnalyticsEvent: vi.fn().mockResolvedValue(undefined),
    postContactMessage: vi.fn().mockResolvedValue(undefined),
  };
});

const mockedPost = vi.mocked(postAnalyticsEvent);
const mockedContact = vi.mocked(postContactMessage);

// Invented values — no real person's details are used anywhere in this suite.
const TYPED_NAME = "Ada Lovelace";
const TYPED_EMAIL = "ada@example.com";
const TYPED_MESSAGE = "I would like to discuss an analytical engine.";

function payloadsAsText(): string {
  return mockedPost.mock.calls.map(([payload]) => JSON.stringify(payload)).join(" ");
}

// useAnalytics throttles identical events to one per second using module-level
// state (`lastEventKey`/`lastEventAt`), which persists across tests in the same
// file. Without advancing the clock between tests, the second and third
// `contact_click` cases are silently throttled — and a test asserting "the
// payload contains no personal data" then passes against an empty list of
// payloads, proving nothing. Each test gets its own minute instead.
let fakeNow = 1_700_000_000_000;

beforeEach(() => {
  mockedPost.mockClear();
  mockedContact.mockClear();
  mockedContact.mockResolvedValue(undefined);
  localStorage.clear();
  fakeNow += 60_000;
  vi.spyOn(Date, "now").mockImplementation(() => fakeNow);
  // jsdom leaves document.title empty, and `not.toContain("")` can never pass.
  document.title = "Portfolio — Contact";
});

describe("analytics payload shape", () => {
  function Probe() {
    const { track } = useAnalytics();
    return (
      <button onClick={() => track("page_view", { metadata: { path: "/about" } })}>fire</button>
    );
  }

  it("sends only the documented fields", () => {
    render(<Probe />);
    fireEvent.click(screen.getByRole("button"));

    expect(mockedPost).toHaveBeenCalledTimes(1);
    const payload = mockedPost.mock.calls[0][0];

    // architecture.md §9's event schema, and nothing beyond it.
    expect(Object.keys(payload).sort()).toEqual(
      ["eventType", "locale", "metadata", "projectSlug", "sessionId"].sort(),
    );
  });

  it("identifies the session with a random id, not anything about the visitor", () => {
    render(<Probe />);
    fireEvent.click(screen.getByRole("button"));

    const { sessionId } = mockedPost.mock.calls[0][0];

    // A v4 UUID from crypto.randomUUID(): carries no device or user identity,
    // and is regenerated whenever the visitor clears site data.
    expect(sessionId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });

  it("never attaches the document title, URL or referrer", () => {
    render(<Probe />);
    fireEvent.click(screen.getByRole("button"));

    const text = payloadsAsText();
    expect(text).not.toContain(document.title);
    expect(text).not.toContain(window.location.href);
    expect(text).not.toContain("referrer");
  });
});

describe("the contact form asks for personal details — none of them are tracked", () => {
  function fillAndSubmit() {
    render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/name|nombre/i), { target: { value: TYPED_NAME } });
    fireEvent.change(screen.getByLabelText(/email|correo/i), { target: { value: TYPED_EMAIL } });
    fireEvent.change(screen.getByLabelText(/message|mensaje/i), {
      target: { value: TYPED_MESSAGE },
    });
    fireEvent.submit(screen.getByRole("button", { name: /send|enviar/i }));
  }

  it("records that a submission happened", () => {
    fillAndSubmit();

    expect(mockedPost).toHaveBeenCalledTimes(1);
    expect(mockedPost.mock.calls[0][0].eventType).toBe("contact_click");
  });

  it("sends none of the typed values", () => {
    fillAndSubmit();

    // Guard against the vacuous version of this test: if the event were
    // throttled away, `text` would be empty and every assertion below would
    // pass while proving nothing.
    expect(mockedPost).toHaveBeenCalledTimes(1);

    const text = payloadsAsText();
    for (const secret of [TYPED_NAME, TYPED_EMAIL, TYPED_MESSAGE, "Ada", "example.com"]) {
      expect(text).not.toContain(secret);
    }
  });

  it("attaches no metadata at all to the contact event", () => {
    fillAndSubmit();

    const payload = mockedPost.mock.calls[0][0];
    expect(payload.metadata).toBeUndefined();
    expect(payload.projectSlug).toBeUndefined();
  });
});

describe("the contact form actually delivers", () => {
  function fill() {
    render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/name|nombre/i), { target: { value: TYPED_NAME } });
    fireEvent.change(screen.getByLabelText(/email|correo/i), { target: { value: TYPED_EMAIL } });
    fireEvent.change(screen.getByLabelText(/message|mensaje/i), {
      target: { value: TYPED_MESSAGE },
    });
  }

  it("sends what the visitor typed to the relay endpoint", async () => {
    fill();
    fireEvent.submit(screen.getByRole("button", { name: /send|enviar/i }));

    await vi.waitFor(() => expect(mockedContact).toHaveBeenCalledTimes(1));
    expect(mockedContact.mock.calls[0][0]).toMatchObject({
      name: TYPED_NAME,
      email: TYPED_EMAIL,
      message: TYPED_MESSAGE,
    });
  });

  it("confirms delivery to the visitor", async () => {
    fill();
    fireEvent.submit(screen.getByRole("button", { name: /send|enviar/i }));

    expect(await screen.findByText(/on its way|va en camino/i)).toBeInTheDocument();
  });

  it("tells the visitor when delivery failed instead of claiming success", async () => {
    // The bug this feature replaces: the old form discarded the message while
    // the visitor believed it had been sent.
    mockedContact.mockRejectedValueOnce(new ApiError("boom", 502));
    fill();
    fireEvent.submit(screen.getByRole("button", { name: /send|enviar/i }));

    expect(await screen.findByText(/was not sent|no se envió/i)).toBeInTheDocument();
  });

  it("explains a rate-limit rejection specifically", async () => {
    mockedContact.mockRejectedValueOnce(new ApiError("slow down", 429));
    fill();
    fireEvent.submit(screen.getByRole("button", { name: /send|enviar/i }));

    expect(await screen.findByText(/wait a few minutes|espera unos minutos/i)).toBeInTheDocument();
  });

  it("keeps a honeypot field that real visitors never see", () => {
    fill();
    const honeypot = document.querySelector('input[name="website"]') as HTMLInputElement;

    expect(honeypot).not.toBeNull();
    expect(honeypot.tabIndex).toBe(-1);
    expect(honeypot.closest("[aria-hidden='true']")).not.toBeNull();
  });
});
