import { useTranslation } from "react-i18next";
import { motion, useReducedMotion } from "motion/react";

import type { SkillGroup } from "../../types";
import styles from "./SkillCategory.module.css";

interface SkillCategoryProps {
  group: SkillGroup;
}

export default function SkillCategory({ group }: SkillCategoryProps) {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();

  return (
    <section className={styles.group} aria-labelledby={`skill-${group.category}`}>
      <h3 id={`skill-${group.category}`} className={styles.heading}>
        {t(`skills.categories.${group.category}`)}
      </h3>
      <ul className={styles.list}>
        {group.skills.map((skill, index) => (
          <li key={skill.name} className={styles.skillRow}>
            <span>{skill.name}</span>
            {skill.proficiency != null && (
              <span className={styles.bar} role="img" aria-label={`${skill.name}: ${skill.proficiency}/5`}>
                {/* Final width is set once via CSS (correct at any proficiency);
                    the reveal itself animates `scaleX`, not `width`, so the
                    browser never re-runs layout on every animation frame. */}
                <motion.span
                  className={styles.barFill}
                  style={{ width: `${(skill.proficiency / 5) * 100}%`, transformOrigin: "left" }}
                  initial={reduceMotion ? false : { scaleX: 0 }}
                  whileInView={{ scaleX: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.7, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
                />
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
