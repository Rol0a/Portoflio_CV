import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { postAnalyticsEvent } from "../services/api";
import type { AnalyticsEventType } from "../types";

const SESSION_STORAGE_KEY = "portfolio_session_id";
const MIN_INTERVAL_MS = 1000; // architecture.md §9: "minimum 1-second gap between identical events"

// Module-level (not per-component-instance) so the throttle holds across
// remounts of whatever component last called track().
let lastEventKey: string | null = null;
let lastEventAt = 0;

function getSessionId(): string {
  let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }
  return sessionId;
}

/** Host of the page that linked here, or undefined for direct/internal arrivals.
 *
 *  Only ever the `hostname`. `document.referrer` is a full URL, and its path and
 *  query string are exactly where free text lives — a Google result carries the
 *  search terms, an email client can carry a token. Sending the host alone means
 *  the parts that could hold personal data never leave the browser, which is a
 *  stronger guarantee than the server-side allowlist that also rejects them.
 *
 *  Read once at module load, not per event: in an SPA `document.referrer` is a
 *  property of the document, so it stays at whatever linked to the *initial*
 *  load and never changes across client-side navigation. A same-origin referrer
 *  is our own page after a hard reload, which is not an acquisition source, so
 *  it is dropped. */
const referrerHost: string | undefined = (() => {
  if (typeof document === "undefined" || !document.referrer) return undefined;
  try {
    const { hostname } = new URL(document.referrer);
    return hostname && hostname !== window.location.hostname ? hostname.toLowerCase() : undefined;
  } catch {
    return undefined;
  }
})();

interface TrackOptions {
  projectSlug?: string;
  metadata?: Record<string, unknown>;
}

export function useAnalytics() {
  const { i18n } = useTranslation();

  const track = useCallback(
    (eventType: AnalyticsEventType, options: TrackOptions = {}) => {
      const key = `${eventType}:${options.projectSlug ?? ""}:${JSON.stringify(options.metadata ?? {})}`;
      const now = Date.now();
      if (key === lastEventKey && now - lastEventAt < MIN_INTERVAL_MS) return;
      lastEventKey = key;
      lastEventAt = now;

      // Attached to page_view only. Every event in a session shares one
      // referrer by definition, and the admin aggregation takes one value per
      // session anyway — sending it on every click would just widen the rows.
      const metadata =
        eventType === "page_view" && referrerHost
          ? { ...options.metadata, ref: referrerHost }
          : options.metadata;

      postAnalyticsEvent({
        eventType,
        sessionId: getSessionId(),
        locale: i18n.language.startsWith("es") ? "es" : "en",
        projectSlug: options.projectSlug,
        metadata,
      }).catch(() => {
        // Fire-and-forget: a tracking failure must never surface to the visitor.
      });
    },
    [i18n.language],
  );

  return { track };
}
