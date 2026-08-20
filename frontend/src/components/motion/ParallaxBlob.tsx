import { useRef, type CSSProperties } from "react";
import { motion, useScroll, useTransform } from "motion/react";

import styles from "./ParallaxBlob.module.css";

interface ParallaxBlobProps {
  className?: string;
  style?: CSSProperties;
  /** -1 to 1: how far the blob drifts as its section scrolls through the viewport. */
  speed?: number;
}

/**
 * A soft, blurred decorative blob that drifts vertically as its containing
 * section scrolls through the viewport — the "Parallax Scroll" pattern.
 * Position is a `motion` scroll-linked value (`useTransform`), which updates
 * on the compositor thread rather than through React state, so this never
 * triggers a re-render on scroll no matter how long the page is.
 */
export function ParallaxBlob({ className, style, speed = 0.3 }: ParallaxBlobProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [`${-speed * 120}px`, `${speed * 120}px`]);

  return (
    <motion.div
      ref={ref}
      aria-hidden="true"
      className={`${styles.blob} ${className ?? ""}`}
      style={{ ...style, y }}
    />
  );
}
