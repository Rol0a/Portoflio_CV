import { Children, type ReactNode } from "react";
import { motion, useReducedMotion, type Variants } from "motion/react";

const container: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
};

const item: Variants = {
  hidden: { opacity: 0, y: 22, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] },
  },
};

interface AnimatedGroupProps {
  children: ReactNode;
  className?: string;
}

/**
 * Staggers a grid/list of children into view (Motion Primitives' "Animated
 * Group" pattern) — each direct child gets its own reveal, offset slightly
 * from its siblings, so a showcase grid arrives as a wave rather than a
 * single flat fade.
 */
export function AnimatedGroup({ children, className }: AnimatedGroupProps) {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      variants={container}
    >
      {Children.map(children, (child) => (
        <motion.div variants={item}>{child}</motion.div>
      ))}
    </motion.div>
  );
}
