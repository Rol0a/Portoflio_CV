import { useMemo, useRef } from "react";

interface UseTiltOptions {
  max?: number;
}

/**
 * Ref-based mouse-tilt + sheen effect for cards. Deliberately does NOT use
 * React state: writing rotation/glow-position on every `mousemove` through
 * setState would re-render the component (and its subtree) dozens of times
 * a second. Instead this writes straight to CSS custom properties on the
 * DOM node via the ref, bypassing React's render cycle entirely — the CSS
 * (`transform: rotateX(var(--tilt-x)) rotateY(var(--tilt-y))`) does the
 * actual work. See docs/frontend-design.md §5 for the pattern this follows.
 */
export function useTilt<T extends HTMLElement>(options: UseTiltOptions = {}) {
  const { max = 8 } = options;
  const ref = useRef<T>(null);
  const prefersReduced = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );

  function handleMouseMove(event: React.MouseEvent<T>) {
    if (prefersReduced) return;
    const node = ref.current;
    if (!node) return;

    const rect = node.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width;
    const py = (event.clientY - rect.top) / rect.height;

    node.style.setProperty("--tilt-x", `${((0.5 - py) * max * 2).toFixed(2)}deg`);
    node.style.setProperty("--tilt-y", `${((px - 0.5) * max * 2).toFixed(2)}deg`);
    node.style.setProperty("--glow-x", `${(px * 100).toFixed(1)}%`);
    node.style.setProperty("--glow-y", `${(py * 100).toFixed(1)}%`);
  }

  function handleMouseLeave() {
    const node = ref.current;
    if (!node) return;
    node.style.setProperty("--tilt-x", "0deg");
    node.style.setProperty("--tilt-y", "0deg");
  }

  return { ref, handleMouseMove, handleMouseLeave };
}
