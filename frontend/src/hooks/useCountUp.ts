import { useEffect, useRef, useState } from "react";

interface UseCountUpOptions {
  duration?: number;
}

/**
 * Animates from 0 to `target` once, the first time the returned ref scrolls
 * into view — requestAnimationFrame-driven with an ease-out-cubic curve, not
 * a CSS transition, so the displayed number itself ticks up digit by digit.
 * Skips straight to the final value under prefers-reduced-motion.
 */
export function useCountUp<T extends HTMLElement = HTMLElement>(target: number, options: UseCountUpOptions = {}) {
  const { duration = 1400 } = options;
  const ref = useRef<T>(null);
  const [value, setValue] = useState(0);
  const hasAnimated = useRef(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || hasAnimated.current) return;
        hasAnimated.current = true;
        observer.disconnect();

        if (prefersReduced) {
          setValue(target);
          return;
        }

        const start = performance.now();
        let frame: number;

        function tick(now: number) {
          const progress = Math.min((now - start) / duration, 1);
          const eased = 1 - (1 - progress) ** 3;
          setValue(Math.round(eased * target));
          if (progress < 1) frame = requestAnimationFrame(tick);
        }

        frame = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(frame);
      },
      { threshold: 0.4 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [target, duration]);

  return { ref, value };
}
