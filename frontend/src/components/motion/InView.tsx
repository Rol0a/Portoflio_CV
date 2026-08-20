import { type ReactNode, useRef } from "react";
import { motion, useInView, useReducedMotion, type Variants } from "motion/react";

const DEFAULT_VARIANTS: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0 },
};

interface InViewProps {
  children: ReactNode;
  className?: string;
  variants?: Variants;
  delay?: number;
  once?: boolean;
}

/**
 * Reveals its children with a soft fade+rise the first time they scroll into
 * view. A Motion Primitives-style building block (see motion-primitives.com's
 * "In View") kept local since that library ships as copy-in source, not an
 * installable package. Falls back to an instant, unanimated render when the
 * visitor has requested reduced motion.
 */
export function InView({ children, className, variants = DEFAULT_VARIANTS, delay = 0, once = true }: InViewProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once, margin: "-80px" });
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      ref={ref}
      className={className}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      variants={reduceMotion ? { hidden: { opacity: 1 }, visible: { opacity: 1 } } : variants}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
