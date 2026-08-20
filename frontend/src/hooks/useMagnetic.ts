import { useMemo, useRef } from "react";

interface UseMagneticOptions {
  /** 0-1: how much of the cursor offset the element follows. */
  strength?: number;
}

/**
 * Subtle "magnetic" cursor attraction for a single hero CTA — same
 * ref-based, zero-re-render architecture as useTilt (see that file for the
 * full rationale). Kept to one element on the page deliberately: a magnetic
 * pull on every button would read as gimmicky rather than considered.
 */
export function useMagnetic<T extends HTMLElement>(options: UseMagneticOptions = {}) {
  const { strength = 0.35 } = options;
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
    const offsetX = (event.clientX - rect.left - rect.width / 2) * strength;
    const offsetY = (event.clientY - rect.top - rect.height / 2) * strength;

    node.style.setProperty("--magnet-x", `${offsetX.toFixed(1)}px`);
    node.style.setProperty("--magnet-y", `${offsetY.toFixed(1)}px`);
  }

  function handleMouseLeave() {
    const node = ref.current;
    if (!node) return;
    node.style.setProperty("--magnet-x", "0px");
    node.style.setProperty("--magnet-y", "0px");
  }

  return { ref, handleMouseMove, handleMouseLeave };
}
