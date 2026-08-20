import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import CertificationCard from "../../components/CertificationCard/CertificationCard";
import { AnimatedGroup } from "../../components/motion/AnimatedGroup";
import PageHeader from "../../components/PageHeader/PageHeader";
import SkillCategory from "../../components/SkillCategory/SkillCategory";
import { useCertifications } from "../../hooks/useCertifications";
import { getSkills } from "../../services/api";
import type { Skills as SkillsData } from "../../types";
import styles from "./Skills.module.css";

/**
 * Skills and certifications share one page: the credentials only mean anything
 * next to the work they back, and splitting them cost a nav slot for a page
 * that was five cards long. `/certifications` redirects here (see App.tsx).
 */
export default function Skills() {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<SkillsData | null>(null);
  const [error, setError] = useState(false);
  const { data: certifications, loading: certsLoading, error: certsError } = useCertifications();

  useEffect(() => {
    let cancelled = false;
    getSkills()
      .then((data) => {
        if (!cancelled) setSkills(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="page-section">
      <PageHeader eyebrow={t("skills.eyebrow")} title={t("skills.title")} intro={t("skills.intro")} />

      {!skills && !error && <p>{t("common.loading")}</p>}
      {error && <p role="alert">{t("common.error")}</p>}
      {skills && (
        <AnimatedGroup className={styles.bands}>
          {/* Featured leads: a ten-badge read of the profile before the reader
              commits to scanning seventy-seven. It repeats badges from the
              sections below on purpose — it's an index, not a partition. */}
          <SkillCategory id="featured" heading={t("skills.categories.featured")} skills={skills.featured} />
          {skills.groups.map((group) => (
            <SkillCategory
              key={group.category}
              id={group.category}
              heading={t(`skills.categories.${group.category}`)}
              skills={group.skills}
            />
          ))}
        </AnimatedGroup>
      )}

      <h2 className={styles.sectionTitle}>{t("skills.section_certifications")}</h2>
      <p className={styles.sectionIntro}>{t("certifications.intro")}</p>
      {certsLoading && <p>{t("common.loading")}</p>}
      {certsError && <p role="alert">{t("common.error")}</p>}
      {!certsLoading && !certsError && certifications && certifications.length === 0 && <p>{t("common.empty")}</p>}
      {!certsLoading && !certsError && certifications && certifications.length > 0 && (
        <AnimatedGroup className={styles.grid}>
          {certifications.map((certification) => (
            <CertificationCard key={certification.slug} certification={certification} />
          ))}
        </AnimatedGroup>
      )}
    </section>
  );
}
