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

      postAnalyticsEvent({
        eventType,
        sessionId: getSessionId(),
        locale: i18n.language.startsWith("es") ? "es" : "en",
        projectSlug: options.projectSlug,
        metadata: options.metadata,
      }).catch(() => {
        // Fire-and-forget: a tracking failure must never surface to the visitor.
      });
    },
    [i18n.language],
  );

  return { track };
}
