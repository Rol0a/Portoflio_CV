import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiError, getNetworkHealth, logout } from "../../services/api";
import type { NetworkHealth as NetworkHealthData } from "../../types";
import AdminNav from "./AdminNav";
import { AXIS_LINE, DATA_1, DATA_2, DATA_3, GRID_LINE, INK_MUTED, STATUS_CRITICAL } from "./palette";
import styles from "./NetworkHealth.module.css";

// Disk was violet. Against the blue of CPU it measured a deutan dE of 1.0 —
// effectively the same line for a red-green colorblind reader — so it moved to
// the palette's aqua slot and additionally carries a dash pattern. Two channels,
// not one: aqua is also the sub-3:1 color on white, which is why this chart now
// has a table view.
const DISK_DASH = "5 3";

// Matches the noc service's own sample cadence (docker-compose.yml's
// NOC_INTERVAL_SECONDS=30) closely enough that a refresh rarely shows the
// exact same NOC sample twice, without polling faster than the data actually
// changes.
const REFRESH_INTERVAL_MS = 15000;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const STATUS_GLYPH: Record<string, string> = { up: "\u2713", degraded: "!", down: "\u2715" };

function StatusPill({ status }: { status: string }) {
  const { t } = useTranslation();
  const label =
    status === "up"
      ? t("admin.network_health.status_up")
      : status === "degraded"
        ? t("admin.network_health.status_degraded")
        : t("admin.network_health.status_down");
  // Colored dot + glyph + word. On a monochrome page the dot is the eye-catch,
  // but it never carries the meaning by itself — the glyph survives a colorblind
  // reader, a greyscale print, and forced-colors mode.
  return (
    <span className={`${styles.pill} ${styles[`pill_${status}`] ?? styles.pill_down}`}>
      <span className={styles.pillDot} aria-hidden="true" />
      <span className={styles.pillGlyph} aria-hidden="true">
        {STATUS_GLYPH[status] ?? STATUS_GLYPH.down}
      </span>
      {label}
    </span>
  );
}

export default function NetworkHealth() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState<NetworkHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load(isFirstLoad: boolean) {
      if (isFirstLoad) {
        setLoading(true);
        setError(false);
      }
      try {
        const result = await getNetworkHealth();
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          navigate("/admin", { replace: true });
          return;
        }
        // A background refresh failing shouldn't blank out data that's still
        // on screen and was correct a moment ago — only the first load shows
        // the error state. The next tick tries again.
        if (isFirstLoad) setError(true);
        setLoading(false);
      }
    }

    load(true);
    // Active-visitor count is computed fresh on every request (see
    // routes/admin.py) rather than sampled on a timer like the NOC data, so
    // this interval is what actually makes it "live" — a page that fetched
    // once on mount would show a number that's already stale by the time an
    // admin glances back at it.
    const interval = window.setInterval(() => load(false), REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
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

      {data && (
        <div className={`${styles.chartCard} ${styles.activeVisitorsCard}`}>
          <h2 className={styles.chartTitle}>{t("admin.network_health.active_visitors_title")}</h2>
          <p className={styles.packetLoss}>
            <strong>{data.activeVisitors.count}</strong>{" "}
            {t("admin.network_health.active_visitors_window", { count: data.activeVisitors.windowMinutes })}
          </p>
        </div>
      )}

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
                  <CartesianGrid vertical={false} stroke={GRID_LINE} />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: INK_MUTED }} axisLine={{ stroke: AXIS_LINE }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: INK_MUTED }} axisLine={false} tickLine={false} domain={[0, 100]} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="cpu" name={t("admin.network_health.cpu")} stroke={DATA_1} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="memory" name={t("admin.network_health.memory")} stroke={DATA_2} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="disk" name={t("admin.network_health.disk")} stroke={DATA_3} strokeWidth={2} strokeDasharray={DISK_DASH} dot={false} />
                </LineChart>
              </ResponsiveContainer>
              {/* Not optional decoration: aqua sits at 2.82:1 on white, below the
                  3:1 bar for a mark, and the documented relief for that is a
                  readable table alongside the chart. It also makes the exact
                  sample values available, which a 200px sparkline never can. */}
              <details className={styles.tableToggle}>
                <summary>{t("admin.view_as_table")}</summary>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t("admin.network_health.time")}</th>
                      <th scope="col">{t("admin.network_health.cpu")}</th>
                      <th scope="col">{t("admin.network_health.memory")}</th>
                      <th scope="col">{t("admin.network_health.disk")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((point) => (
                      <tr key={point.time}>
                        <td>{point.time}</td>
                        <td>{point.cpu}%</td>
                        <td>{point.memory}%</td>
                        <td>{point.disk}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </div>

            <div className={`${styles.chartCard} ${styles.wide}`}>
              <h2 className={styles.chartTitle}>{t("admin.network_health.traffic_title")}</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID_LINE} />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: INK_MUTED }} axisLine={{ stroke: AXIS_LINE }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: INK_MUTED }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="requests" name={t("admin.network_health.requests")} fill={DATA_1} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="errors" name={t("admin.network_health.errors")} fill={STATUS_CRITICAL} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
