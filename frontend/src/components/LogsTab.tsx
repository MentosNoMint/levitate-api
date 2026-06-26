import React, { useState, useEffect } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { Trash2, Radio, Send, Loader2, Play } from "lucide-react";
import { translations } from "@/store/translations";
import { Modal } from "./Modal";

export default function LogsTab() {
  const { language, logs, virtualKeys, credentials, simulateLog, clearLogs } = useDashboardStore();
  const t = translations[language];

  // State for Test Request Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState("");
  const [promptText, setPromptText] = useState("Hello. Output exactly the word 'OK' and nothing else.");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    model: string;
    latency: number;
    prompt_tokens: number;
    completion_tokens: number;
    response: string;
  } | null>(null);

  const activeCredentials = credentials.filter(c => c.status === "active");
  const availableModels = Array.from(
    new Set(activeCredentials.flatMap(c => c.models || []))
  );

  useEffect(() => {
    if (availableModels.length > 0 && !selectedModel) {
      setSelectedModel(availableModels[0]);
    }
  }, [availableModels, selectedModel]);

  const handleSimulateRequest = () => {
    setError(null);
    setResult(null);
    setIsModalOpen(true);
  };

  const handleSendTestRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel) {
      setError(t.logs.msg_no_active_creds);
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await simulateLog(selectedModel, promptText);
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to execute request");
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusText = (status: number, statusText: string) => {
    if (status === 200) return "200 OK";
    if (status === 429) return language === "en" ? "429 Rate Limit" : "429 Лимит запросов";
    if (status === 401) return language === "en" ? "401 Unauthorized" : "401 Не авторизован";
    return language === "en" ? "503 Service Unavailable" : "503 Сервис недоступен";
  };

  const hasNoKeys = virtualKeys.length === 0;
  const hasNoCreds = availableModels.length === 0;

  const renderResponseContent = (text: string) => {
    if (!text) return null;

    const imgRegex = /!\[(.*?)\]\((.*?)\)/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = imgRegex.exec(text)) !== null) {
      const matchIndex = match.index;
      if (matchIndex > lastIndex) {
        parts.push(text.substring(lastIndex, matchIndex));
      }

      const alt = match[1];
      const url = match[2];

      parts.push(
        <div key={matchIndex} className="my-3 flex flex-col items-center gap-2 bg-[var(--bg-panel)] p-2 rounded-[var(--radius-md)] border border-[var(--border)] max-w-full">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={alt || "Generated Image"}
            className="max-w-full h-auto rounded-[var(--radius-sm)] shadow-sm max-h-[350px] object-contain"
          />
          {alt && (
            <span className="text-xs text-[var(--text-muted)] font-sans italic">
              {alt}
            </span>
          )}
        </div>
      );

      lastIndex = imgRegex.lastIndex;
    }

    if (lastIndex < text.length) {
      const remaining = text.substring(lastIndex);
      const trimmed = remaining.trim();
      if (parts.length === 0 && (trimmed.startsWith("data:image/") || trimmed.startsWith("data:application/octet-stream;base64,"))) {
        return (
          <div className="flex flex-col items-center gap-2 bg-[var(--bg-panel)] p-2 rounded-[var(--radius-md)] border border-[var(--border)] max-w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={trimmed}
              alt="Generated Image"
              className="max-w-full h-auto rounded-[var(--radius-sm)] shadow-sm max-h-[350px] object-contain"
            />
          </div>
        );
      }
      parts.push(remaining);
    }

    return (
      <>
        {parts.map((part, index) => {
          if (typeof part === "string") {
            return <span key={index}>{part}</span>;
          }
          return part;
        })}
      </>
    );
  };

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
            disabled={hasNoKeys || hasNoCreds}
            className={`primary-action-btn focus-ring flex items-center gap-2 ${(hasNoKeys || hasNoCreds) ? "opacity-50 cursor-not-allowed" : ""}`}
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

      {/* Test Request Modal */}
      <Modal
        open={isModalOpen}
        onClose={() => !isLoading && setIsModalOpen(false)}
        title={t.logs.test_modal_title}
      >
        <form onSubmit={handleSendTestRequest} className="flex flex-col gap-4">
          {/* Model Selection */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-[var(--text-muted)]">
              {t.logs.lbl_select_model}
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={isLoading}
              className="w-full px-3 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-[var(--radius-md)] text-[var(--text-main)] text-sm focus:outline-none focus:border-[var(--primary)] transition-colors disabled:opacity-50"
            >
              {availableModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>

          {/* Prompt */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-[var(--text-muted)]">
              {t.logs.lbl_prompt}
            </label>
            <textarea
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              disabled={isLoading}
              rows={3}
              placeholder={t.logs.placeholder_prompt}
              className="w-full px-3 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-[var(--radius-md)] text-[var(--text-main)] text-sm focus:outline-none focus:border-[var(--primary)] transition-colors disabled:opacity-50 resize-none font-sans"
            />
          </div>

          {/* Submit Button */}
          <div className="flex justify-end gap-2 pt-2 border-t border-[var(--border)]">
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              disabled={isLoading}
              className="px-4 py-2 bg-transparent text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-sm font-medium rounded-[var(--radius-md)] transition-colors disabled:opacity-50 focus-ring"
            >
              {translations[language].common.cancel}
            </button>
            <button
              type="submit"
              disabled={isLoading || !selectedModel}
              className={`primary-action-btn focus-ring flex items-center gap-2 ${(isLoading || !selectedModel) ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t.logs.btn_sending}
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  {t.logs.btn_send}
                </>
              )}
            </button>
          </div>
        </form>

        {/* Loader Display */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center py-8 gap-3 text-[var(--text-muted)]">
            <Loader2 className="w-8 h-8 animate-spin text-[var(--primary)]" />
            <span className="text-sm font-medium">
              {language === "en" ? "Executing request on upstream AI..." : "Выполняется запрос к оригинальной ИИ..."}
            </span>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="mt-4 p-4 bg-red-950/20 border border-red-500/30 text-red-400 rounded-[var(--radius-md)] text-xs break-all">
            <p className="font-semibold mb-1">
              {language === "en" ? "Error occurred:" : "Произошла ошибка:"}
            </p>
            <p className="font-mono">{error}</p>
          </div>
        )}

        {/* Result Display */}
        {result && (
          <div className="mt-4 flex flex-col gap-3">
            {/* Metadata metrics */}
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-[var(--radius-md)] flex flex-col gap-0.5">
                <span className="text-[var(--text-muted)] font-sans font-semibold">
                  {t.logs.lbl_latency}
                </span>
                <span className="text-sm font-bold text-[var(--text-main)]">
                  {result.latency} ms
                </span>
              </div>
              <div className="p-2.5 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-[var(--radius-md)] flex flex-col gap-0.5">
                <span className="text-[var(--text-muted)] font-sans font-semibold">
                  {t.logs.lbl_tokens}
                </span>
                <span className="text-sm font-bold text-[var(--text-main)]">
                  {result.prompt_tokens}p / {result.completion_tokens}c
                </span>
              </div>
            </div>

            {/* Answer body */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-[var(--text-muted)]">
                {t.logs.lbl_response}
              </label>
              <div className="w-full p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-[var(--radius-md)] text-sm text-[var(--text-main)] font-sans whitespace-pre-wrap max-h-[250px] overflow-y-auto border-l-4 border-l-[var(--primary)] shadow-inner">
                {result.response ? (
                  renderResponseContent(result.response)
                ) : (
                  <span className="text-[var(--text-muted)] italic">
                    {language === "en" ? "[Empty Response]" : "[Пустой ответ]"}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
