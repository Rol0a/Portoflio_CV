import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { InView } from "../../components/motion/InView";
import { useAnalytics } from "../../hooks/useAnalytics";
import { useProject } from "../../hooks/useProjects";
import styles from "./ProjectDetail.module.css";

const CASE_STUDY_FIELDS = [
  "overview",
  "problem",
  "requirements",
  "architecture",
  "implementation",
  "decisions",
  "challenges",
  "testingDesc",
  "results",
  "lessons",
] as const;

const FIELD_TO_KEY: Record<(typeof CASE_STUDY_FIELDS)[number], string> = {
  overview: "overview",
  problem: "problem",
  requirements: "requirements",
  architecture: "architecture",
  implementation: "implementation",
  decisions: "decisions",
  challenges: "challenges",
  testingDesc: "testing_desc",
  results: "results",
  lessons: "lessons",
};

function ImagePlaceholderIcon() {
  return (
    <svg className={styles.heroPlaceholderIcon} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M21 15l-5.5-5.5a1 1 0 0 0-1.4 0L4 19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export default function ProjectDetail() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const { data: project, loading, error } = useProject(slug);
  const { track } = useAnalytics();
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    if (project) {
      track("project_view", { projectSlug: project.slug });
    }
    // Track once per project loaded, not on every locale change while viewing it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.slug]);

  // A fresh project may not have uploaded images yet — reset per project so
  // a broken image on one doesn't carry over and hide a working one on the next.
  useEffect(() => {
    setImageFailed(false);
  }, [project?.slug]);

  const backLink = (
    <p>
      <Link to="/projects">← {t("projects.back")}</Link>
    </p>
  );

  if (loading) {
    return (
      <section className="page-section">
        {backLink}
        <p>{t("common.loading")}</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="page-section">
        {backLink}
        <p role="alert">{t("common.error")}</p>
      </section>
    );
  }

  if (!project) {
    return (
      <section className="page-section">
        {backLink}
        <p>{t("projects.not_found")}</p>
      </section>
    );
  }

  const hero = project.images.find((image) => image.isHero) ?? project.images[0];

  return (
    <article className="page-section">
      {backLink}
      <span className={styles.badges}>
        <span className={styles.category}>{project.category.replace("_", " ")}</span>
        {project.status === "in_development" && (
          <span className={styles.inDevelopment}>{t("projects.status_in_development")}</span>
        )}
      </span>
      <h1 className={styles.title}>{project.title}</h1>
      <p className={styles.desc}>{project.shortDesc}</p>

      {/* Says why there is no repo link below, instead of leaving the absence to
          be read as an oversight. */}
      {project.status === "in_development" && (
        <p className={styles.developmentNote}>{t("projects.in_development_note")}</p>
      )}

      {hero && !imageFailed ? (
        <img
          className={styles.hero}
          src={hero.url}
          alt={hero.altText ?? project.title}
          onError={() => setImageFailed(true)}
        />
      ) : (
        <div className={styles.heroPlaceholder}>
          <ImagePlaceholderIcon />
          <span>{t("projects.no_image")}</span>
        </div>
      )}

      <ul className={styles.techList}>
        {project.technologies.map((tech) => (
          <li key={tech.name}>{tech.name}</li>
        ))}
      </ul>

      <div className={styles.links}>
        {project.githubUrl && (
          <a
            href={project.githubUrl}
            target="_blank"
            rel="noreferrer"
            className={styles.linkSecondary}
            onClick={() => track("github_click", { projectSlug: project.slug })}
          >
            {t("projects.github")}
          </a>
        )}
        {project.demoUrl && (
          <a
            href={project.demoUrl}
            target="_blank"
            rel="noreferrer"
            className={styles.linkPrimary}
            onClick={() => track("project_link_click", { projectSlug: project.slug, metadata: { link: "demo" } })}
          >
            {t("projects.demo")}
          </a>
        )}
      </div>

      {CASE_STUDY_FIELDS.map((field) => {
        const value = project[field];
        if (!value) return null;
        return (
          <InView key={field} className={styles.section} delay={0.05}>
            <h2>{t(`projects.sections.${FIELD_TO_KEY[field]}`)}</h2>
            <p>{value}</p>
          </InView>
        );
      })}
    </article>
  );
}
