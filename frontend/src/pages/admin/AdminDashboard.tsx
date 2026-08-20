import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, getAdminAnalytics, logout } from "../../services/api";
import type { AdminAnalytics, Granularity } from "../../types";
import AdminNav from "./AdminNav";
import { AXIS_LINE, DATA_1, DATA_2, GRID_LINE, INK_MUTED, SURFACE } from "./palette";
import styles from "./AdminDashboard.module.css";

const RANGE_OPTIONS: { days: number; labelKey: string }[] = [
  { days: 7, labelKey: "range_7" },
  { days: 30, labelKey: "range_30" },
  { days: 90, labelKey: "range_90" },
];

interface LineTooltipProps {
  active?: boolean;
  label?: string;
  payload?: { name: string; value: number; color: string }[];
}

function TimeseriesTooltip({ active, label, payload }: LineTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipLabel}>{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className={styles.tooltipRow}>
          <span className={styles.tooltipKey} style={{ background: entry.color }} />
          <span className={styles.tooltipValue}>{entry.value}</span>
          <span className={styles.tooltipLabel}>{entry.name}</span>
        </div>
      ))}
    </div>
  );
}

function BarTooltip({ active, label, payload }: LineTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipRow}>
        <span className={styles.tooltipValue}>{payload[0].value}</span>
        <span className={styles.tooltipLabel}>{label}</span>
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const granularity: Granularity = "day";
  const [data, setData] = useState<AdminAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getAdminAnalytics(days, granularity)
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
  }, [days, navigate]);

  async function handleLogout() {
    await logout();
    navigate("/admin", { replace: true });
  }

  const totalLangSessions = data
    ? Object.values(data.summary.languageDistribution).reduce((sum, n) => sum + n, 0)
    : 0;

  return (
    <section className={styles.page}>
      <div className={styles.headerRow}>
        <h1>{t("admin.dashboard.title")}</h1>
        <div className={styles.headerActions}>
          <AdminNav />
          <button type="button" className={styles.logoutBtn} onClick={handleLogout}>
            {t("admin.dashboard.logout")}
          </button>
        </div>
      </div>

      <p className={styles.notice}>{t("admin.dashboard.demo_data_notice")}</p>

      <div className={styles.rangeRow} role="group" aria-label="Date range">
        {RANGE_OPTIONS.map((option) => (
          <button
            key={option.days}
            type="button"
            className={styles.rangeBtn}
            aria-pressed={days === option.days}
            onClick={() => setDays(option.days)}
          >
            {t(`admin.dashboard.${option.labelKey}`)}
          </button>
        ))}
      </div>

      {loading && <p>{t("common.loading")}</p>}
      {error && <p role="alert">{t("common.error")}</p>}

      {data && (
        <>
          <div className={styles.statGrid}>
            <StatTile label={t("admin.dashboard.stat_page_views")} value={data.summary.totalPageViews} />
            <StatTile label={t("admin.dashboard.stat_unique_sessions")} value={data.summary.uniqueSessions} />
            <StatTile label={t("admin.dashboard.stat_project_views")} value={data.summary.totalProjectViews} />
            <StatTile label={t("admin.dashboard.stat_github_clicks")} value={data.summary.githubClicks} />
            <StatTile label={t("admin.dashboard.stat_cv_downloads")} value={data.summary.cvDownloads} />
            <StatTile label={t("admin.dashboard.stat_contact_clicks")} value={data.summary.contactClicks} />
          </div>

          <div className={styles.chartsGrid}>
            <div className={`${styles.chartCard} ${styles.wide}`}>
              <h2 className={styles.chartTitle}>{t("admin.dashboard.chart_visits")}</h2>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data.timeseries} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID_LINE} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: INK_MUTED }}
                    axisLine={{ stroke: AXIS_LINE }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: INK_MUTED }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip content={<TimeseriesTooltip />} />
                  <Legend
                    wrapperStyle={{ fontSize: 12 }}
                    formatter={(value) => <span style={{ color: INK_MUTED }}>{value}</span>}
                  />
                  <Line
                    type="monotone"
                    dataKey="pageViews"
                    name={t("admin.dashboard.stat_page_views")}
                    stroke={DATA_1}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, stroke: SURFACE, strokeWidth: 2 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="uniqueSessions"
                    name={t("admin.dashboard.stat_unique_sessions")}
                    stroke={DATA_2}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, stroke: SURFACE, strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
              <details className={styles.tableToggle}>
                <summary>{t("admin.view_as_table")}</summary>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t("admin.dashboard.date")}</th>
                      <th scope="col">{t("admin.dashboard.stat_page_views")}</th>
                      <th scope="col">{t("admin.dashboard.stat_unique_sessions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.timeseries.map((point) => (
                      <tr key={point.date}>
                        <td>{point.date}</td>
                        <td>{point.pageViews}</td>
                        <td>{point.uniqueSessions}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </div>

            <div className={styles.chartCard}>
              <h2 className={styles.chartTitle}>{t("admin.dashboard.chart_top_projects")}</h2>
              {data.topProjects.length === 0 ? (
                <p>{t("common.empty")}</p>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(120, data.topProjects.length * 44)}>
                  <BarChart
                    data={data.topProjects}
                    layout="vertical"
                    margin={{ top: 4, right: 24, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid horizontal={false} stroke={GRID_LINE} />
                    <XAxis type="number" hide allowDecimals={false} />
                    <YAxis
                      type="category"
                      dataKey="title"
                      width={110}
                      tick={{ fontSize: 11, fill: INK_MUTED }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip content={<BarTooltip />} cursor={{ fill: "#f4f4f5" }} />
                    <Bar dataKey="views" fill={DATA_1} radius={[0, 4, 4, 0]} maxBarSize={20} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className={styles.chartCard}>
              <h2 className={styles.chartTitle}>{t("admin.dashboard.chart_language")}</h2>
              {totalLangSessions === 0 ? (
                <p>{t("common.empty")}</p>
              ) : (
                <LanguageSplit distribution={data.summary.languageDistribution} total={totalLangSessions} />
              )}
            </div>

            <div className={`${styles.chartCard} ${styles.wide}`}>
              <h2 className={styles.chartTitle}>{t("admin.dashboard.recent_activity")}</h2>
              {data.recentEvents.length === 0 ? (
                <p>{t("admin.dashboard.no_recent_activity")}</p>
              ) : (
                <ul className={styles.activityList}>
                  {data.recentEvents.map((event, index) => (
                    <li key={`${event.timestamp}-${index}`} className={styles.activityItem}>
                      <span className={styles.activityType}>
                        {event.eventType}
                        {event.projectSlug ? ` · ${event.projectSlug}` : ""}
                      </span>
                      <span className={styles.activityMeta}>{new Date(event.timestamp).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.statTile}>
      <p className={styles.statLabel}>{label}</p>
      <p className={styles.statValue}>{value.toLocaleString()}</p>
    </div>
  );
}

interface LanguageSplitProps {
  distribution: Record<string, number>;
  total: number;
}

function LanguageSplit({ distribution, total }: LanguageSplitProps) {
  const rows = [
    { code: "EN", count: distribution.en ?? 0, color: DATA_1 },
    { code: "ES", count: distribution.es ?? 0, color: DATA_2 },
  ];

  return (
    <>
      <div className={styles.langLegend}>
        {rows.map((row) => (
          <span key={row.code} className={styles.langLegendItem}>
            <span className={styles.langSwatch} style={{ background: row.color }} />
            {row.code} {row.count} · {Math.round((row.count / total) * 100)}%
          </span>
        ))}
      </div>
      <div className={styles.langBar} role="img" aria-label={rows.map((row) => `${row.code} ${row.count}`).join(", ")}>
        {rows.map((row) => (
          <div
            key={row.code}
            className={styles.langSegment}
            style={{ background: row.color, width: `${(row.count / total) * 100}%` }}
          />
        ))}
      </div>
    </>
  );
}
