import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";

import styles from "./ScrollProgress.module.css";

/**
 * A thin bar across the top of the viewport tracking scroll progress —
 * `useScroll` + `useSpring` are `motion` values, not React state, so this
 * updates every frame without ever re-rendering React. Most useful on the
 * scroll-driven Home page, but mounted globally in Layout since it's cheap
 * and reads correctly on any page length.
 */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 200, damping: 30, restDelta: 0.001 });
  const reduceMotion = useReducedMotion();

  if (reduceMotion) return null;

  return <motion.div className={styles.bar} style={{ scaleX }} />;
}
