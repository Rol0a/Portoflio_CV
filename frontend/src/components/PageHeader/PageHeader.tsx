import type { ReactNode } from "react";

import { InView } from "../motion/InView";
import styles from "./PageHeader.module.css";

interface PageHeaderProps {
  eyebrow: string;
  title: string;
  intro?: ReactNode;
}

/**
 * Shared header for every non-Home page: eyebrow + h1 + optional intro,
 * revealed with the same InView fade-rise Home uses for its section heads.
 * Also the one place that gives these pages breathing room under the sticky
 * header — see docs/frontend-design.md §7.
 */
export default function PageHeader({ eyebrow, title, intro }: PageHeaderProps) {
  return (
    <InView className={styles.header}>
      <span className={styles.eyebrow}>{eyebrow}</span>
      <h1 className={styles.title}>{title}</h1>
      {intro && <p className={styles.intro}>{intro}</p>}
    </InView>
  );
}
