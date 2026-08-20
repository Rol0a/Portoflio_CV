import { useTranslation } from "react-i18next";

import SkillBadge from "../SkillBadge/SkillBadge";
import type { Skill } from "../../types";
import styles from "./SkillCategory.module.css";

interface SkillCategoryProps {
  /** i18n key suffix under `skills.categories`, also the heading's DOM id. */
  id: string;
  heading: string;
  skills: Skill[];
}

/**
 * One labelled band of skill badges.
 *
 * Takes a heading string rather than a category enum so the Featured row — which
 * is a curated cross-section, not a category — can reuse it without inventing a
 * category value that no skill actually holds.
 */
export default function SkillCategory({ id, heading, skills }: SkillCategoryProps) {
  const { t } = useTranslation();

  if (skills.length === 0) return null;

  return (
    <section className={styles.group} aria-labelledby={`skill-${id}`}>
      <h3 id={`skill-${id}`} className={styles.heading}>
        {heading}
      </h3>
      <ul className={styles.list} aria-label={t("skills.badge_list", { category: heading })}>
        {skills.map((skill) => (
          <SkillBadge key={skill.name} name={skill.name} />
        ))}
      </ul>
    </section>
  );
}
