import { ICONS } from "./icons";
import { FALLBACK_ICON, SKILL_ICONS } from "./skillIcons";
import styles from "./SkillBadge.module.css";

interface SkillBadgeProps {
  name: string;
}

function SkillIcon({ name }: { name: string }) {
  const icon = ICONS[SKILL_ICONS[name] ?? FALLBACK_ICON] ?? ICONS[FALLBACK_ICON];

  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {icon.fill ? (
        <path d={icon.fill} fill="currentColor" />
      ) : (
        icon.stroke?.map((fragment) => (
          <path
            key={fragment}
            d={fragment}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))
      )}
    </svg>
  );
}

/**
 * One technology, as a compact chip: mark on the left, name on the right.
 *
 * Replaces the old proficiency-bar rows. A self-assessed 3/5 next to "SolidWorks"
 * told a reader nothing they could act on and invited a comparison the data
 * couldn't support; the projects are the evidence of depth. This is a technical
 * index — scan it, don't read it.
 */
export default function SkillBadge({ name }: SkillBadgeProps) {
  return (
    <li className={styles.badge}>
      <SkillIcon name={name} />
      <span className={styles.name}>{name}</span>
    </li>
  );
}
