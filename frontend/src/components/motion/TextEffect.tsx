import { motion, useReducedMotion } from "motion/react";

interface TextEffectProps {
  text: string;
  className?: string;
  delay?: number;
  as?: "span" | "h1" | "h2";
}

/**
 * Word-by-word blur+rise reveal (Motion Primitives' "Text Effect"), used
 * sparingly — the hero headline only. Splitting on words (not characters)
 * keeps it legible rather than gimmicky.
 */
export function TextEffect({ text, className, delay = 0, as = "span" }: TextEffectProps) {
  const reduceMotion = useReducedMotion();
  const words = text.split(" ");
  const Wrapper = as;

  if (reduceMotion) {
    return <Wrapper className={className}>{text}</Wrapper>;
  }

  return (
    <Wrapper className={className}>
      {words.map((word, index) => (
        <motion.span
          key={`${word}-${index}`}
          style={{ display: "inline-block", whiteSpace: "pre" }}
          initial={{ opacity: 0, y: "0.4em", filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.55, delay: delay + index * 0.06, ease: [0.22, 1, 0.36, 1] }}
        >
          {word}
          {index < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </Wrapper>
  );
}
