import React from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { Activity, Coins, KeyRound, BarChart3 } from "lucide-react";
import { translations } from "@/store/translations";

const sparkPoints = (values: number[], width = 120, height = 36): string => {
  if (values.length < 2) return "";
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 6) - 3;
      return `${x},${y}`;
    })
    .join(" ");
};

export default function OverviewTab() {
  const { language, credentials, stats, virtualKeys } = useDashboardStore();
  const t = translations[language];
  const en = language === "en";

  const totalPools = credentials.length;
  const activePools = credentials.filter((c) => c.status === "active").length;
  const activePct = Math.round((activePools / (totalPools || 1)) * 100);
  const activeKeys = virtualKeys.filter((k) => k.status === "active").length;

  const hasError = credentials.some((c) => c.status === "error");
  const operational = !hasError;

  const historyValues = stats.tokenUsageHistory.map((d) => d.value);
  const sparkLine = sparkPoints(historyValues);

  const maxHistoryValue = Math.max(...historyValues, 1);
  const chartHeight = 200;
  const chartWidth = 640;
  const points = stats.tokenUsageHistory
    .map((d, idx) => {
      const x = (idx / (stats.tokenUsageHistory.length - 1 || 1)) * chartWidth;
      const y = chartHeight - (d.value / maxHistoryValue) * (chartHeight - 16) - 4;
      return { x, y };
    });
  const linePoints = points.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPoints = points.length
    ? `0,${chartHeight} ${linePoints} ${chartWidth},${chartHeight}`
    : "";
  const lastPoint = points[points.length - 1];
  const yTicks = [1, 0.75, 0.5, 0.25, 0].map((f) => Math.round(maxHistoryValue * f));

  return (
    <div className="overview-mc" id="view-overview">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[var(--text-main)]">
            {t.layout.overview_title}
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {language === "en" ? "System overview, active pools and keys performance." : "Общая сводка системы, состояние аккаунтов и лимитов."}
          </p>
        </div>
      </div>

      <div className="mc-strip">
        <span className="mc-live">
          <span className={`mc-pulse ${operational ? "" : "is-down"}`} />
          {operational
            ? en ? "All systems operational" : "Все системы работают"
            : en ? "Degraded performance" : "Снижение производительности"}
        </span>
        <span className="mc-sep" />
        <span className="mc-ss-item">
          {en ? "Accounts:" : "Аккаунты:"} <b className="mc-mono">{activePools}/{totalPools}</b> {en ? "active" : "активно"}
        </span>
        <span className="mc-ss-item">
          {en ? "Success" : "Успех"} <b className="mc-mono">{stats.gatewaySuccessRate}%</b>
        </span>
      </div>

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="mc-card">
          <div className="mc-kpi-top">
            <span className="mc-kpi-label">{t.overview.active_pools}</span>
            <span className="mc-kpi-ic"><Activity className="w-4 h-4" /></span>
          </div>
          <div className="mc-kpi-value mc-mono">
            {activePools}<span className="mc-u">/ {totalPools}</span>
          </div>
          <div className="mc-kpi-foot">
            <span className="mc-delta up">{activePct}%</span>
            {en ? "active across all providers" : "активны среди провайдеров"}
          </div>
        </div>

        <div className="mc-card">
          <div className="mc-kpi-top">
            <span className="mc-kpi-label">{t.overview.active_keys}</span>
            <span className="mc-kpi-ic"><KeyRound className="w-4 h-4" /></span>
          </div>
          <div className="mc-kpi-value mc-mono">
            {activeKeys}<span className="mc-u">/ {virtualKeys.length}</span>
          </div>
          <div className="mc-kpi-foot">
            {t.overview.active_keys_desc}
          </div>
        </div>

        <div className="mc-card">
          <div className="mc-kpi-top">
            <span className="mc-kpi-label">{t.overview.total_tokens}</span>
            <span className="mc-kpi-ic"><Coins className="w-4 h-4" /></span>
          </div>
          <div className="mc-kpi-value mc-mono">
            {stats.totalRoutedTokens.toFixed(2)}<span className="mc-u">M</span>
          </div>
          <div className="mc-kpi-foot">
            {t.overview.total_tokens_desc}
          </div>
          {sparkLine && (
            <svg className="mc-spark" viewBox="0 0 120 36" preserveAspectRatio="none">
              <polyline fill="none" stroke="var(--mc-primary-line)" strokeWidth="1.5" points={sparkLine} />
            </svg>
          )}
        </div>

        <div className="mc-card">
          <div className="mc-kpi-top">
            <span className="mc-kpi-label">{t.overview.total_requests}</span>
            <span className="mc-kpi-ic"><BarChart3 className="w-4 h-4" /></span>
          </div>
          <div className="mc-kpi-value mc-mono">
            {stats.totalRequests.toLocaleString()}
          </div>
          <div className="mc-kpi-foot">
            {t.overview.total_requests_desc}
          </div>
        </div>
      </section>

      <div className="mc-panel">
        <div className="mc-panel-head">
          <div>
            <h3>{t.overview.chart_title}</h3>
            <p>{t.overview.chart_desc}</p>
          </div>
          <div className="flex flex-col gap-1.5 items-end shrink-0">
            <span className="mc-legend"><span className="mc-swatch" /> {en ? "Tokens / M" : "Токены / М"}</span>
            <span className="mc-now">{en ? "now" : "сейчас"} <b className="mc-mono">{stats.totalRoutedTokens.toFixed(1)}M</b></span>
          </div>
        </div>

        <div className="px-5 pb-5 pt-1">
          <div className="flex gap-2.5">
            <div className="mc-yaxis" style={{ height: "12.5rem" }}>
              {yTicks.map((tick, idx) => (
                <span key={idx} className="mc-mono">{tick}</span>
              ))}
            </div>
            <svg
              viewBox={`0 0 ${chartWidth} ${chartHeight}`}
              className="w-full"
              style={{ height: "12.5rem" }}
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient id="mcArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--mc-primary)" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="var(--mc-primary)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <g stroke="var(--mc-grid)" strokeWidth="1">
                {[2, 51, 100, 149, 198].map((y) => (
                  <line key={y} x1="0" y1={y} x2={chartWidth} y2={y} />
                ))}
              </g>
              {areaPoints && <polygon points={areaPoints} fill="url(#mcArea)" />}
              {linePoints && (
                <polyline
                  points={linePoints}
                  fill="none"
                  stroke="var(--mc-primary)"
                  strokeWidth="2.25"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              )}
              {lastPoint && (
                <circle
                  cx={lastPoint.x}
                  cy={lastPoint.y}
                  r="4.5"
                  fill="var(--mc-panel)"
                  stroke="var(--mc-primary)"
                  strokeWidth="2.5"
                />
              )}
            </svg>
          </div>
          <div className="mc-xaxis">
            {stats.tokenUsageHistory.map((d, idx) => (
              <span key={idx}>{idx % 4 === 0 ? d.timestamp : ""}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="mc-section-title">
        <h2>{t.overview.health_title}</h2>
        <span className="mc-count mc-mono">
          {en ? "Total accounts:" : "Всего аккаунтов:"} {totalPools} · {en ? "Active:" : "Активно:"} {activePools}
        </span>
      </div>

      <div className="mc-panel">
        <table className="mc-table">
          <thead>
            <tr>
              <th>{t.overview.col_name}</th>
              <th>{t.overview.col_status}</th>
              <th>{t.overview.col_quota}</th>
            </tr>
          </thead>
          <tbody>
            {credentials.map((cred) => {
              const remaining = cred.quotaTotalTokens ? Math.max(0, cred.quotaTotalTokens - cred.quotaUsedTokens) : null;
              const pct = cred.quotaTotalTokens ? Math.max(0, Math.min(100, (remaining! / cred.quotaTotalTokens) * 100)) : 0;
              return (
                <tr key={cred.id}>
                  <td>
                    <div className="mc-prov">
                      <span className="mc-name">
                        {t.mock[cred.name as keyof typeof t.mock] || cred.name}
                      </span>
                      <span className="mc-tag">
                        {cred.type === "managed" ? "Managed" : "BYO"} · {cred.provider}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={`mc-pill ${cred.status === "degraded" ? "is-cooldown" : `is-${cred.status}`}`}>
                      <span className="mc-dot" />
                      {cred.status === "degraded"
                        ? (language === "en" ? "Degraded" : "Снижен")
                        : (t.common[cred.status as keyof typeof t.common] || cred.status)}
                    </span>
                  </td>
                  <td>
                    {cred.modelQuotas && (cred.modelQuotas["gemini-weekly"] !== undefined || cred.modelQuotas["3p-weekly"] !== undefined) ? (
                      <div className="flex flex-col gap-1 w-full max-w-[15rem]" onClick={(e) => e.stopPropagation()}>
                        {/* Gemini */}
                        {cred.modelQuotas["gemini-weekly"] !== undefined && (() => {
                          const g5h = cred.modelQuotas["gemini-5h"] !== undefined ? Math.round(cred.modelQuotas["gemini-5h"] * 100) : null;
                          const gW = cred.modelQuotas["gemini-weekly"] !== undefined ? Math.round(cred.modelQuotas["gemini-weekly"] * 100) : null;
                          return (
                            <div className="flex items-center gap-1.5 text-[10px] leading-none">
                              <div className="w-3.5 h-3.5 flex items-center justify-center shrink-0" title="Gemini Models">
                                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                                  <path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2L12 2Z" fill={`url(#geminiGradientOverview-${cred.id})`} />
                                  <defs>
                                    <linearGradient id={`geminiGradientOverview-${cred.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                                      <stop offset="0%" stopColor="#1A73E8" />
                                      <stop offset="50%" stopColor="#8AB4F8" />
                                      <stop offset="100%" stopColor="#C68BFC" />
                                    </linearGradient>
                                  </defs>
                                </svg>
                              </div>
                              <span className="font-semibold text-[var(--text-main)] min-w-[38px] mr-0.5">Gemini:</span>
                              {g5h !== null && (
                                <div className="flex items-center gap-1">
                                  <span className="text-[var(--text-muted)]">5h</span>
                                  <span className="font-mono font-bold min-w-[22px] text-right text-[var(--text-main)]">{g5h}%</span>
                                  <div className="w-8 h-1 bg-[var(--bg-subtle)] rounded-full overflow-hidden border border-[var(--border)]">
                                    <div className={`h-full ${g5h < 15 ? "bg-[var(--color-danger)]" : g5h < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${g5h}%` }} />
                                  </div>
                                </div>
                              )}
                              {gW !== null && (
                                <div className="flex items-center gap-1 ml-1">
                                  <span className="text-[var(--text-muted)]">W</span>
                                  <span className="font-mono font-bold min-w-[22px] text-right text-[var(--text-main)]">{gW}%</span>
                                  <div className="w-8 h-1 bg-[var(--bg-subtle)] rounded-full overflow-hidden border border-[var(--border)]">
                                    <div className={`h-full ${gW < 15 ? "bg-[var(--color-danger)]" : gW < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${gW}%` }} />
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}

                        {/* Claude/GPT */}
                        {cred.modelQuotas["3p-weekly"] !== undefined && (() => {
                          const c5h = cred.modelQuotas["3p-5h"] !== undefined ? Math.round(cred.modelQuotas["3p-5h"] * 100) : null;
                          const cW = cred.modelQuotas["3p-weekly"] !== undefined ? Math.round(cred.modelQuotas["3p-weekly"] * 100) : null;
                          return (
                            <div className="flex items-center gap-1.5 text-[10px] leading-none mt-0.5">
                              <div className="w-3.5 h-3.5 flex items-center justify-center shrink-0" title="Claude & GPT Models">
                                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                                  <path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" fill={`url(#anthropicGradientOverview-${cred.id})`} />
                                  <path d="M17 11L18 14L21 15L18 16L17 19L16 16L13 15L16 14L17 11Z" fill={`url(#anthropicGradientOverview-${cred.id})`} />
                                  <defs>
                                    <linearGradient id={`anthropicGradientOverview-${cred.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                                      <stop offset="0%" stopColor="#F59E0B" />
                                      <stop offset="100%" stopColor="#D97706" />
                                    </linearGradient>
                                  </defs>
                                </svg>
                              </div>
                              <span className="font-semibold text-[var(--text-main)] min-w-[38px] mr-0.5">Other:</span>
                              {c5h !== null && (
                                <div className="flex items-center gap-1">
                                  <span className="text-[var(--text-muted)]">5h</span>
                                  <span className="font-mono font-bold min-w-[22px] text-right text-[var(--text-main)]">{c5h}%</span>
                                  <div className="w-8 h-1 bg-[var(--bg-subtle)] rounded-full overflow-hidden border border-[var(--border)]">
                                    <div className={`h-full ${c5h < 15 ? "bg-[var(--color-danger)]" : c5h < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${c5h}%` }} />
                                  </div>
                                </div>
                              )}
                              {cW !== null && (
                                <div className="flex items-center gap-1 ml-1">
                                  <span className="text-[var(--text-muted)]">W</span>
                                  <span className="font-mono font-bold min-w-[22px] text-right text-[var(--text-main)]">{cW}%</span>
                                  <div className="w-8 h-1 bg-[var(--bg-subtle)] rounded-full overflow-hidden border border-[var(--border)]">
                                    <div className={`h-full ${cW < 15 ? "bg-[var(--color-danger)]" : cW < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${cW}%` }} />
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    ) : remaining !== null && cred.quotaTotalTokens ? (
                      <div className="mc-lat">
                        <span className="mc-mono text-xs">
                          {Math.round(pct)}%
                        </span>
                        <span className="mc-bar">
                          <i style={{ width: `${pct}%` }} />
                        </span>
                      </div>
                    ) : (
                      <span className="mc-muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
