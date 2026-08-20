import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiError, getNetworkHealth, logout } from "../../services/api";
import type { NetworkHealth as NetworkHealthData } from "../../types";
import AdminNav from "./AdminNav";
import styles from "./NetworkHealth.module.css";

const CPU_COLOR = "#2a78d6";
const MEM_COLOR = "#eb6834";
const DISK_COLOR = "#8a63d2";
const REQUEST_COLOR = "#2a78d6";
const ERROR_COLOR = "#d6483c";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function StatusPill({ status }: { status: string }) {
  const { t } = useTranslation();
  const label =
    status === "up"
      ? t("admin.network_health.status_up")
      : status === "degraded"
        ? t("admin.network_health.status_degraded")
        : t("admin.network_health.status_down");
  return <span className={`${styles.pill} ${styles[`pill_${status}`] ?? styles.pill_down}`}>{label}</span>;
}

export default function NetworkHealth() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState<NetworkHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getNetworkHealth()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          navigate("/admin", { replace: true });
          return;
        }
        setError(true);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [navigate]);

  async function handleLogout() {
    await logout();
    navigate("/admin", { replace: true });
  }

  const chartData =
    data?.history.map((sample) => ({
      time: formatTime(sample.sampledAt),
      cpu: sample.cpuPercent,
      memory: sample.memoryPercent,
      disk: sample.diskPercent,
      requests: sample.requestsCount,
      errors: sample.errorsCount,
    })) ?? [];

  return (
    <section className={styles.page}>
      <div className={styles.headerRow}>
        <h1>{t("admin.network_health.title")}</h1>
        <div className={styles.headerActions}>
          <AdminNav />
          <button type="button" className={styles.logoutBtn} onClick={handleLogout}>
            {t("admin.network_health.logout")}
          </button>
        </div>
      </div>

      <p className={styles.notice}>{t("admin.network_health.notice")}</p>

      {loading && <p>{t("common.loading")}</p>}
      {error && <p role="alert">{t("common.error")}</p>}

      {data && !data.latest && <p>{t("admin.network_health.no_data")}</p>}

      {data?.latest && (
        <>
          <p className={styles.lastUpdated}>
            {t("admin.network_health.last_updated")}: {new Date(data.latest.sampledAt).toLocaleString()}
          </p>

          <div className={styles.chartCard}>
            <h2 className={styles.chartTitle}>{t("admin.network_health.services_title")}</h2>
            <div className={styles.statusGrid}>
              {Object.entries(data.latest.services).map(([name, check]) => (
                <div key={name} className={styles.statusTile}>
                  <span className={styles.statusName}>{name}</span>
                  <StatusPill status={check.status} />
                  {check.latencyMs !== null && <span className={styles.statusLatency}>{check.latencyMs} ms</span>}
                </div>
              ))}
            </div>
          </div>

          <div className={styles.chartsGrid}>
            <div className={styles.chartCard}>
              <h2 className={styles.chartTitle}>{t("admin.network_health.internet_title")}</h2>
              {data.latest.packetLossPct !== null && (
                <p className={styles.packetLoss}>
                  {t("admin.network_health.packet_loss")}: <strong>{data.latest.packetLossPct}%</strong>
                </p>
              )}
              <ul className={styles.targetList}>
                {Object.entries(data.latest.internetTargets).map(([target, check]) => (
                  <li key={target} className={styles.targetItem}>
                    <span>{target}</span>
                    {check.reachable ? (
                      <span className={styles.targetLatency}>{check.latencyMs} ms</span>
                    ) : (
                      <span className={styles.targetUnreachable}>{t("admin.network_health.unreachable")}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div className={styles.chartCard}>
              <h2 className={styles.chartTitle}>{t("admin.network_health.resources_title")}</h2>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={chartData} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--grid-line)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} axisLine={{ stroke: "var(--axis-line)" }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} axisLine={false} tickLine={false} domain={[0, 100]} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="cpu" name={t("admin.network_health.cpu")} stroke={CPU_COLOR} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="memory" name={t("admin.network_health.memory")} stroke={MEM_COLOR} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="disk" name={t("admin.network_health.disk")} stroke={DISK_COLOR} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className={`${styles.chartCard} ${styles.wide}`}>
              <h2 className={styles.chartTitle}>{t("admin.network_health.traffic_title")}</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--grid-line)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} axisLine={{ stroke: "var(--axis-line)" }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="requests" name={t("admin.network_health.requests")} fill={REQUEST_COLOR} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="errors" name={t("admin.network_health.errors")} fill={ERROR_COLOR} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
