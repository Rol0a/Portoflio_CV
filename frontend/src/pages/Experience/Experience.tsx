import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { InView } from "../../components/motion/InView";
import PageHeader from "../../components/PageHeader/PageHeader";
import styles from "./Experience.module.css";

const META_KEYS = ["location", "email", "education", "focus"] as const;

interface ExperienceRole {
  id: string;
  role: string;
  org: string;
  place: string;
  period: string;
  summary: string;
  highlights: string[];
}

/**
 * `experience.roles` is authored in the i18n bundles, so a malformed or
 * half-translated entry is a real possibility — same defensive stance the old
 * About page took with its paragraph array. A bad entry is dropped rather than
 * blanking the whole timeline.
 */
function isRole(value: unknown): value is ExperienceRole {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.role === "string" &&
    typeof candidate.org === "string" &&
    typeof candidate.period === "string" &&
    Array.isArray(candidate.highlights)
  );
}

function Chevron() {
  return (
    <svg className={styles.chevron} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Experience() {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();

  // i18next types `t()` as returning a string even under `returnObjects`, so the
  // cast to `unknown[]` is what lets the type guard below do the narrowing.
  const raw = t("experience.roles", { returnObjects: true });
  const roles: ExperienceRole[] = Array.isArray(raw) ? (raw as unknown[]).filter(isRole) : [];

  // Accordion, not a set of independent toggles: the newest role opens on
  // arrival so the page never lands as a wall of collapsed headers, and only
  // one panel is open at a time so the timeline's shape stays readable.
  // `id` is locale-independent, so switching language keeps the same role open.
  const [openId, setOpenId] = useState<string | null>(roles[0]?.id ?? null);

  return (
    <section className="page-section">
      <PageHeader eyebrow={t("experience.eyebrow")} title={t("experience.title")} intro={t("experience.intro")} />

      <div className={styles.layout}>
        <InView className={styles.timelineWrap}>
          <p className={styles.hint}>{t("experience.expand_hint")}</p>

          <ol className={styles.timeline}>
            {roles.map((entry) => {
              const open = openId === entry.id;
              return (
                <li key={entry.id} className={`${styles.item} ${open ? styles.itemOpen : ""}`}>
                  <span className={styles.marker} aria-hidden="true" />

                  <h2 className={styles.itemHeading}>
                    <button
                      type="button"
                      className={styles.trigger}
                      aria-expanded={open}
                      onClick={() => setOpenId(open ? null : entry.id)}
                    >
                      <span className={styles.period}>{entry.period}</span>
                      <span className={styles.role}>{entry.role}</span>
                      <span className={styles.org}>
                        {entry.org}
                        {entry.place ? ` · ${entry.place}` : ""}
                      </span>
                      <Chevron />
                    </button>
                  </h2>

                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.div
                        className={styles.panel}
                        initial={reduceMotion ? false : { height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={reduceMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
                        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                      >
                        <div className={styles.panelInner}>
                          <p className={styles.summary}>{entry.summary}</p>
                          <ul className={styles.highlights}>
                            {entry.highlights.map((highlight) => (
                              <li key={highlight}>{highlight}</li>
                            ))}
                          </ul>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </li>
              );
            })}
          </ol>
        </InView>

        <aside className={styles.meta}>
          <h2 className={styles.metaTitle}>{t("experience.meta_title")}</h2>
          <ul className={styles.metaList}>
            {META_KEYS.map((key) => (
              <li key={key}>{t(`experience.${key}`)}</li>
            ))}
          </ul>
        </aside>
      </div>
    </section>
  );
}
