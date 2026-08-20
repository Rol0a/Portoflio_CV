import { useCountUp } from "../../hooks/useCountUp";
import styles from "./StatCounter.module.css";

interface StatCounterProps {
  value: number;
  label: string;
  suffix?: string;
}

export function StatCounter({ value, label, suffix = "" }: StatCounterProps) {
  const { ref, value: animated } = useCountUp<HTMLSpanElement>(value);

  return (
    <div className={styles.stat}>
      <span ref={ref} className={styles.value}>
        {animated}
        {suffix}
      </span>
      <span className={styles.label}>{label}</span>
    </div>
  );
}
