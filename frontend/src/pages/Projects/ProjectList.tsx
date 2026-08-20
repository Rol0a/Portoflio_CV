import { useTranslation } from "react-i18next";

import { AnimatedGroup } from "../../components/motion/AnimatedGroup";
import PageHeader from "../../components/PageHeader/PageHeader";
import ProjectCard from "../../components/ProjectCard/ProjectCard";
import { useProjects } from "../../hooks/useProjects";
import styles from "./ProjectList.module.css";

export default function ProjectList() {
  const { t } = useTranslation();
  const { data: projects, loading, error } = useProjects();

  return (
    <section className="page-section">
      <PageHeader eyebrow={t("projects.eyebrow")} title={t("projects.title")} intro={t("projects.intro")} />
      {loading && <p>{t("common.loading")}</p>}
      {error && <p role="alert">{t("common.error")}</p>}
      {!loading && !error && projects && projects.length === 0 && <p>{t("common.empty")}</p>}
      {!loading && !error && projects && projects.length > 0 && (
        <AnimatedGroup className={styles.grid}>
          {projects.map((project) => (
            <ProjectCard key={project.slug} project={project} />
          ))}
        </AnimatedGroup>
      )}
    </section>
  );
}
