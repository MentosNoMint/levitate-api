import React from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { Trash2, Radio } from "lucide-react";
import { translations } from "@/store/translations";

export default function LogsTab() {
  const { language, logs, virtualKeys, simulateLog, clearLogs } = useDashboardStore();
  const t = translations[language];

  const handleSimulateRequest = () => {
    simulateLog();
  };

  const getStatusText = (status: number, statusText: string) => {
    if (status === 200) return "200 OK";
    if (status === 429) return language === "en" ? "429 Rate Limit" : "429 Лимит запросов";
    if (status === 401) return language === "en" ? "401 Unauthorized" : "401 Не авторизован";
    return language === "en" ? "503 Service Unavailable" : "503 Сервис недоступен";
  };

  const hasNoKeys = virtualKeys.length === 0;

  return (
    <div className="overview-mc flex flex-col gap-6" id="view-logs">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[var(--text-main)]">
            {t.logs.title}
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.logs.desc}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSimulateRequest}
            disabled={hasNoKeys}
            className={`primary-action-btn focus-ring flex items-center gap-2 ${hasNoKeys ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            <Radio className="w-4 h-4 animate-pulse" />
            {t.logs.btn_simulate}
          </button>
          <button
            onClick={clearLogs}
            className="px-4 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-sm font-medium rounded-[var(--radius-md)] flex items-center gap-2 transition-colors focus-ring"
            aria-label="Clear all logs"
          >
            <Trash2 className="w-4 h-4" />
            {t.logs.btn_clear}
          </button>
        </div>
      </div>

      <div className="mc-panel">
        <table className="mc-table">
          <thead>
            <tr>
              <th className="w-[12%]">{t.logs.col_time}</th>
              <th className="w-[18%]">{t.logs.col_key}</th>
              <th className="w-[18%]">{t.logs.col_pool}</th>
              <th className="w-[18%]">{t.logs.col_model}</th>
              <th className="w-[10%]">{t.logs.col_latency}</th>
              <th className="w-[13%]">{t.logs.col_tokens}</th>
              <th className="w-[11%]">{t.logs.col_response}</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-[var(--text-muted)]">
                  {t.logs.empty_state}
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id}>
                  <td className="text-[var(--mc-muted)] font-mono text-xs whitespace-nowrap">
                    {log.timestamp}
                  </td>
                  <td>
                    <span className="font-semibold text-[var(--mc-text)]">
                      {t.mock[log.virtualKey as keyof typeof t.mock] || log.virtualKey}
                    </span>
                  </td>
                  <td>
                    <span className="text-[var(--mc-muted)]">
                      {t.mock[log.destinationPool as keyof typeof t.mock] || log.destinationPool}
                    </span>
                  </td>
                  <td>
                    <span className="text-[var(--mc-muted)] font-mono text-xs">{log.model}</span>
                  </td>
                  <td className="text-[var(--mc-muted)] font-mono text-xs">
                    {log.latency > 0 ? `${log.latency}ms` : "—"}
                  </td>
                  <td>
                    <div className="flex flex-col">
                      <span className="font-semibold text-[var(--mc-text)]">{log.totalTokens.toLocaleString()}</span>
                      <span className="text-[var(--mc-muted)] text-[10px]">
                        {t.logs.tokens_format
                          .replace("{prompt}", log.promptTokens.toString())
                          .replace("{completion}", log.completionTokens.toString())}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={`mc-pill ${log.status === 200 ? "is-active" : "is-error"}`}>
                      <span className="mc-dot" />
                      {getStatusText(log.status, log.statusText)}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
