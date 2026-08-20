import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AnimatedGroup } from "../../components/motion/AnimatedGroup";
import PageHeader from "../../components/PageHeader/PageHeader";
import SkillCategory from "../../components/SkillCategory/SkillCategory";
import { getSkills } from "../../services/api";
import type { SkillGroup } from "../../types";
import styles from "./Skills.module.css";

export default function Skills() {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<SkillGroup[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSkills()
      .then((data) => {
        if (!cancelled) setGroups(data);
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
      {!groups && !error && <p>{t("common.loading")}</p>}
      {error && <p role="alert">{t("common.error")}</p>}
      {groups && (
        <AnimatedGroup className={styles.grid}>
          {groups.map((group) => (
            <SkillCategory key={group.category} group={group} />
          ))}
        </AnimatedGroup>
      )}
    </section>
  );
}
