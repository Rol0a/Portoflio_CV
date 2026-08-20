import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useTilt } from "../../hooks/useTilt";
import type { ProjectListItem } from "../../types";
import styles from "./ProjectCard.module.css";

interface ProjectCardProps {
  project: ProjectListItem;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const { t } = useTranslation();
  const tilt = useTilt<HTMLAnchorElement>();

  return (
    <Link
      to={`/projects/${project.slug}`}
      className={styles.card}
      ref={tilt.ref}
      onMouseMove={tilt.handleMouseMove}
      onMouseLeave={tilt.handleMouseLeave}
    >
      <span className={styles.sheen} aria-hidden="true" />
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
      <span className={styles.cta} aria-hidden="true">
        {t("projects.view_details")} →
      </span>
    </Link>
  );
}
