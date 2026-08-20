import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { InView } from "../motion/InView";
import type { ProjectListItem } from "../../types";
import styles from "./ProjectShowcase.module.css";

interface ProjectShowcaseProps {
  projects: ProjectListItem[];
}

function ImagePlaceholderIcon() {
  return (
    <svg className={styles.visualPlaceholderIcon} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M21 15l-5.5-5.5a1 1 0 0 0-1.4 0L4 19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function ProjectVisual({ project }: { project: ProjectListItem }) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);
  const hasImage = Boolean(project.heroImageUrl) && !failed;

  return (
    <div className={styles.visual}>
      <div className={styles.visualGhost} aria-hidden="true" />
      {hasImage ? (
        <img
          className={styles.visualImage}
          src={project.heroImageUrl!}
          alt=""
          onError={() => setFailed(true)}
        />
      ) : (
        <div className={styles.visualPlaceholder}>
          <ImagePlaceholderIcon />
          <span>{t("projects.no_image")}</span>
        </div>
      )}
    </div>
  );
}

/**
 * A pinned two-column "project story" per featured project: sticky title +
 * description + tech + CTAs beside a visual, one tall row each. Adapted from
 * a reference site's multi-screenshot stacking gallery — this data model has
 * one hero image per project, not a gallery, so the visual side stays honest
 * about that (a single image with a CSS-only "stacked card" hint) rather than
 * faking a deck of screenshots that don't exist. See docs/frontend-design.md §9.
 */
export function ProjectShowcase({ projects }: ProjectShowcaseProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.list}>
      {projects.map((project, index) => (
        <div key={project.slug} className={`${styles.row} ${index % 2 === 1 ? styles.rowReverse : ""}`}>
          <InView className={styles.sticky}>
            <span className={styles.numeral} aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className={styles.content}>
              <span className={styles.badges}>
                <span className={styles.category}>{project.category.replace("_", " ")}</span>
                {project.status === "in_development" && (
                  <span className={styles.inDevelopment}>{t("projects.status_in_development")}</span>
                )}
              </span>
              <h3 className={styles.title}>{project.title}</h3>
              <p className={styles.desc}>{project.shortDesc}</p>
              <ul className={styles.techList}>
                {project.technologies.map((tech) => (
                  <li key={tech}>{tech}</li>
                ))}
              </ul>
              <div className={styles.actions}>
                <Link to={`/projects/${project.slug}`} className={styles.primary}>
                  {t("projects.view_details")} →
                </Link>
                {project.githubUrl && (
                  <a href={project.githubUrl} target="_blank" rel="noreferrer" className={styles.secondary}>
                    {t("projects.github")}
                  </a>
                )}
              </div>
            </div>
          </InView>

          <InView delay={0.1} className={styles.visualCol}>
            <ProjectVisual project={project} />
          </InView>
        </div>
      ))}
    </div>
  );
}
