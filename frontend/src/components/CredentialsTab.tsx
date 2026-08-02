import React, { useState, useEffect } from "react";
import { useDashboardStore, Credential } from "@/store/dashboardStore";
import { ChevronRight, Plus, X, ShieldAlert, Check, Trash2, ExternalLink } from "lucide-react";
import { translations } from "@/store/translations";
import { Modal } from "./Modal";

export default function CredentialsTab() {
  const { language, credentials, addCredential, updateCredentialPriorityWeight, toggleCredentialStatus, token, refreshCredentialQuota, refreshAllQuotas, deleteCredential } = useDashboardStore();
  const t = translations[language];

  const renderErrorWithLinks = (text: string) => {
    if (!text) return null;
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    const parts = text.split(urlRegex);
    return parts.map((part, index) => {
      if (part.match(urlRegex)) {
        return (
          <a
            key={index}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            className="underline text-[var(--primary)] hover:text-[var(--primary-hover)] break-all inline-flex items-center gap-0.5"
          >
            {part}
            <ExternalLink className="w-3 h-3 inline shrink-0" />
          </a>
        );
      }
      return part;
    });
  };

  const [showAddForm, setShowAddForm] = useState(false);
  const [expandedCredIds, setExpandedCredIds] = useState<Record<string, boolean>>({});
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({});

  const [newName, setNewName] = useState("");
  const [newProvider, setNewProvider] = useState("OpenAI");
  const [newType] = useState<"managed" | "byo">("byo");
  const [newPriority, setNewPriority] = useState(1);
  const [newWeight, setNewWeight] = useState(5);
  const [newConcurrency, setNewConcurrency] = useState(20);
  const [newQuota, setNewQuota] = useState<number | null>(null);
  const [newWindow, setNewWindow] = useState<number | null>(null);
  const [newModels, setNewModels] = useState("");
  const [newApiKey, setNewApiKey] = useState("");
  const [newBaseUrl, setNewBaseUrl] = useState("");

  const [editPriorities, setEditPriorities] = useState<Record<string, number>>({});
  const [editWeights, setEditWeights] = useState<Record<string, number>>({});
  const [editConcurrencies, setEditConcurrencies] = useState<Record<string, number>>({});
  const [editQuotas, setEditQuotas] = useState<Record<string, number | null>>({});
  const [editWindows, setEditWindows] = useState<Record<string, number | null>>({});
  const [editModels, setEditModels] = useState<Record<string, string>>({});

  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setTick((tick) => tick + 1);
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  const handleConnectGoogle = () => {
    if (typeof window !== "undefined") {
      const getApiUrl = (): string => {
        if (typeof window !== "undefined") {
          const envApi = process.env.NEXT_PUBLIC_API_URL;
          if (envApi) return envApi;
          return window.location.protocol + "//" + window.location.hostname + ":8000";
        }
        return "http://localhost:8000";
      };
      window.location.href = `${getApiUrl()}/admin/auth/login?action=add_credential&token=${token || ""}`;
    }
  };


  const toggleRow = (id: string) => {
    setExpandedCredIds((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));

    const cred = credentials.find((c) => c.id === id);
    if (cred) {
      setEditPriorities((prev) => ({ ...prev, [id]: cred.priority }));
      setEditWeights((prev) => ({ ...prev, [id]: cred.weight }));
      setEditConcurrencies((prev) => ({ ...prev, [id]: cred.concurrency }));
      setEditQuotas((prev) => ({ ...prev, [id]: cred.quotaTotalTokens }));
      setEditWindows((prev) => ({ ...prev, [id]: cred.quotaWindow }));
      setEditModels((prev) => ({ ...prev, [id]: cred.models ? cred.models.join(", ") : "" }));
    }
  };

  const handleAddCredential = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;

    const modelsArr = newModels
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    addCredential({
      name: newName,
      provider: newProvider,
      type: newType,
      priority: newPriority,
      weight: newWeight,
      concurrency: newConcurrency,
      apiKey: newApiKey,
      baseUrl: newBaseUrl.trim() || undefined,
      quotaTotalTokens: newQuota,
      quotaWindow: newWindow,
      models: modelsArr,
    });

    setNewName("");
    setNewProvider("OpenAI");
    setNewPriority(1);
    setNewWeight(5);
    setNewConcurrency(20);
    setNewQuota(null);
    setNewWindow(null);
    setNewModels("");
    setNewApiKey("");
    setNewBaseUrl("");
    setShowAddForm(false);
  };

  const handleSaveChanges = (id: string) => {
    const priority = editPriorities[id] ?? 1;
    const weight = editWeights[id] ?? 5;
    const concurrency = editConcurrencies[id] ?? 20;
    const quota = editQuotas[id] !== undefined ? editQuotas[id] : null;
    const windowVal = editWindows[id] !== undefined ? editWindows[id] : null;
    const modelsStr = editModels[id] || "";
    const modelsArr = modelsStr
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    updateCredentialPriorityWeight(id, priority, weight, concurrency, quota, windowVal, modelsArr);
  };

  const getResetCountdown = (resetAtStr: string | null) => {
    if (!resetAtStr) return "";
    const resetTime = new Date(resetAtStr).getTime();
    const now = new Date().getTime();
    const diffMs = resetTime - now;
    if (diffMs <= 0) return "";

    const diffMins = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMins / 60);
    const mins = diffMins % 60;

    if (language === "ru") {
      return `Сброс: ${hours}ч ${mins}м`;
    } else {
      return `Reset: ${hours}h ${mins}m`;
    }
  };

  const providerMap: Record<string, string> = {
    gemini: "GOOGLE GEMINI",
    anthropic: "ANTHROPIC CLAUDE",
    openai: "OPENAI",
    cohere: "COHERE",
    deepseek: "DEEPSEEK",
  };

  const getModelProviderGroup = (modelName: string): string => {
    const name = modelName.toLowerCase();
    if (name.includes("gemini")) return "GOOGLE GEMINI";
    if (name.includes("claude") || name.includes("anthropic")) return "ANTHROPIC CLAUDE";
    if (name.includes("gpt") || name.includes("o1") || name.includes("o3") || name.includes("openai")) return "OPENAI";
    if (name.includes("deepseek")) return "DEEPSEEK";
    if (name.includes("cohere")) return "COHERE";
    return "OTHER";
  };

  interface GroupedCredential {
    credential: Credential;
    modelsToShow: string[];
  }

  const sections: Record<string, GroupedCredential[]> = {};

  credentials.forEach((c) => {
    let group = "";
    if (c.type === "managed") {
      group = "ANTIGRAVITY CLI";
    } else {
      const provKey = c.provider.toLowerCase();
      group = providerMap[provKey] || c.provider.toUpperCase();
    }

    if (!sections[group]) {
      sections[group] = [];
    }

    sections[group].push({
      credential: c,
      modelsToShow: c.models || [],
    });
  });

  return (
    <div className="overview-mc flex flex-col gap-6" id="view-credentials">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[var(--text-main)]">
            {t.credentials.title}
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.credentials.desc}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row items-center gap-2 w-full md:w-auto">
          <button
            onClick={async () => {
              await refreshAllQuotas();
            }}
            className="w-full sm:w-auto px-4 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-sm font-medium rounded-[var(--radius-md)] flex items-center justify-center gap-2 transition-colors focus-ring"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
            </svg>
            {t.credentials.btn_refresh_quotas}
          </button>
          <button
            onClick={handleConnectGoogle}
            className="w-full sm:w-auto px-4 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-sm font-medium rounded-[var(--radius-md)] flex items-center justify-center gap-2 transition-colors focus-ring"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path
                fill="#EA4335"
                d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114-3.555 0-6.438-2.883-6.438-6.438 0-3.555 2.883-6.438 6.438-6.438 1.547 0 2.956.545 4.062 1.455l3.087-3.087C19.014 1.954 15.823 1 12.24 1 5.922 1 12.24 5.922 1 12.24s4.922 11.24 11.24 11.24c6.318 0 11.24-4.922 11.24-11.24 0-.682-.068-1.364-.205-1.955H12.24Z"
              />
            </svg>
            {t.credentials.btn_connect_google}
          </button>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="w-full sm:w-auto primary-action-btn focus-ring flex items-center justify-center gap-2"
            aria-expanded={showAddForm}
          >
            {showAddForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            {showAddForm ? t.credentials.btn_cancel : t.credentials.btn_add}
          </button>
        </div>
      </div>

      <Modal
        open={showAddForm}
        onClose={() => setShowAddForm(false)}
        title={t.credentials.form_title}
      >
        <form onSubmit={handleAddCredential} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="cred-name" className="text-xs font-semibold text-[var(--text-muted)]">
              {t.credentials.form_name}
            </label>
            <input
              id="cred-name"
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={t.credentials.form_name_placeholder}
              className="premium-input outline-none"
              required
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="cred-provider" className="text-xs font-semibold text-[var(--text-muted)]">
                {t.credentials.form_provider}
              </label>
              <select
                id="cred-provider"
                value={newProvider}
                onChange={(e) => setNewProvider(e.target.value)}
                className="premium-select outline-none"
              >
                <option value="OpenAI">OpenAI</option>
                <option value="Anthropic">Anthropic</option>
                <option value="Gemini">Gemini</option>
                <option value="Cohere">Cohere</option>
                <option value="DeepSeek">DeepSeek</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="cred-apikey" className="text-xs font-semibold text-[var(--text-muted)]">
                {t.credentials.form_api_key}
              </label>
              <input
                id="cred-apikey"
                type="password"
                value={newApiKey}
                onChange={(e) => setNewApiKey(e.target.value)}
                placeholder="sk-..."
                className="premium-input outline-none"
                required
              />
            </div>
          </div>

          <details className="group">
            <summary className="text-xs font-semibold text-[var(--text-muted)] cursor-pointer hover:text-[var(--text-main)] select-none flex items-center gap-1 py-2 outline-none">
              <ChevronRight className="w-3.5 h-3.5 transition-transform group-open:rotate-90" />
              {t.credentials.lbl_advanced}
            </summary>
            <div className="flex flex-col gap-4 mt-2 p-4 bg-[var(--bg-app)] border border-[var(--border)] rounded-[var(--radius-md)]">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="cred-baseurl" className="text-xs font-semibold text-[var(--text-muted)]">
                  {t.credentials.form_base_url}
                </label>
                <input
                  id="cred-baseurl"
                  type="text"
                  value={newBaseUrl}
                  onChange={(e) => setNewBaseUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                  className="premium-input outline-none"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="cred-priority" className="text-xs font-semibold text-[var(--text-muted)]">
                    {t.credentials.form_priority}
                  </label>
                  <input
                    id="cred-priority"
                    type="number"
                    value={newPriority}
                    onChange={(e) => setNewPriority(Number(e.target.value))}
                    className="premium-input outline-none"
                    required
                    min={1}
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label htmlFor="cred-weight" className="text-xs font-semibold text-[var(--text-muted)]">
                    {t.credentials.form_weight}
                  </label>
                  <input
                    id="cred-weight"
                    type="number"
                    value={newWeight}
                    onChange={(e) => setNewWeight(Number(e.target.value))}
                    className="premium-input outline-none"
                    required
                    min={1}
                    max={100}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="cred-concurrency" className="text-xs font-semibold text-[var(--text-muted)]">
                    {t.credentials.form_concurrency}
                  </label>
                  <input
                    id="cred-concurrency"
                    type="number"
                    value={newConcurrency}
                    onChange={(e) => setNewConcurrency(Number(e.target.value))}
                    className="premium-input outline-none"
                    required
                    min={0}
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label htmlFor="cred-quota" className="text-xs font-semibold text-[var(--text-muted)]">
                    {t.credentials.lbl_token_quota}
                  </label>
                  <input
                    id="cred-quota"
                    type="number"
                    value={newQuota !== null ? newQuota : ""}
                    onChange={(e) => setNewQuota(e.target.value ? Number(e.target.value) : null)}
                    placeholder="Unlimited"
                    className="premium-input outline-none"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="cred-window" className="text-xs font-semibold text-[var(--text-muted)]">
                  {t.credentials.lbl_reset_window}
                </label>
                <input
                  id="cred-window"
                  type="number"
                  value={newWindow !== null ? newWindow : ""}
                  onChange={(e) => setNewWindow(e.target.value ? Number(e.target.value) : null)}
                  placeholder="e.g. 86400"
                  className="premium-input outline-none"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="cred-models" className="text-xs font-semibold text-[var(--text-muted)]">
                  {t.credentials.lbl_supported_models}
                </label>
                <input
                  id="cred-models"
                  type="text"
                  value={newModels}
                  onChange={(e) => setNewModels(e.target.value)}
                  placeholder="e.g. gpt-4o, claude-3-5-sonnet"
                  className="premium-input outline-none"
                />
              </div>
            </div>
          </details>

          <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-[var(--border)]">
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-sm font-semibold rounded-[var(--radius-md)] transition-colors"
            >
              {t.credentials.btn_cancel}
            </button>
            <button type="submit" className="primary-action-btn focus-ring">
              {t.credentials.form_btn}
            </button>
          </div>
        </form>
      </Modal>

      <div className="flex flex-col gap-8">
        {Object.entries(sections).map(([groupName, groupCreds]) => (
          <div key={groupName} className="flex flex-col gap-4">
            <div className="flex items-center gap-4">
              <span className="text-xs font-semibold tracking-wider text-[var(--text-muted)] whitespace-nowrap uppercase">
                {groupName}
              </span>
              <div className="h-px w-full bg-[var(--border)]" />
            </div>

            <div className="mc-panel">
              <table className="mc-table">
                <thead>
                  <tr>
                    <th className="w-[40%]">{t.credentials.col_id}</th>
                    <th className="w-[15%]">{t.credentials.col_provider}</th>
                    <th className="w-[12%]">{t.credentials.col_type}</th>
                    <th className="w-[25%]">{t.overview.col_quota}</th>
                    <th className="w-[8%]">{t.credentials.col_status}</th>
                  </tr>
                </thead>
                <tbody>
                  {groupCreds.map(({ credential: cred, modelsToShow }) => {
                    const isExpanded = !!expandedCredIds[cred.id];
                    const priorityVal = editPriorities[cred.id] ?? cred.priority;
                    const weightVal = editWeights[cred.id] ?? cred.weight;
                    const concurrencyVal = editConcurrencies[cred.id] ?? cred.concurrency;

                    const remaining = cred.quotaTotalTokens !== null ? Math.max(0, cred.quotaTotalTokens - cred.quotaUsedTokens) : null;
                    const pct = cred.quotaTotalTokens !== null && cred.quotaTotalTokens > 0 ? Math.max(0, Math.min(100, (remaining! / cred.quotaTotalTokens) * 100)) : 100;

                    return (
                      <React.Fragment key={cred.id}>
                        <tr
                          onClick={() => toggleRow(cred.id)}
                          className="cursor-pointer hover:bg-[var(--mc-elev)] transition-colors"
                        >
                          <td>
                            <div className="flex items-center gap-2">
                              <ChevronRight
                                className={`w-4 h-4 shrink-0 transition-transform ${
                                  isExpanded ? "rotate-90 text-[var(--mc-primary)]" : ""
                                }`}
                              />
                              <div className="flex flex-col gap-1">
                                <span className="font-semibold text-[var(--mc-text)]">
                                  {t.mock[cred.name as keyof typeof t.mock] || cred.name}
                                </span>
                                {modelsToShow && modelsToShow.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1 max-w-[20rem]" onClick={(e) => e.stopPropagation()}>
                                    {modelsToShow.slice(0, 3).map((m) => (
                                      <span key={m} className="px-1.5 py-0.5 text-[0.625rem] rounded-[var(--radius-sm)] bg-[var(--mc-subtle)] text-[var(--mc-muted)] font-mono">
                                        {m}
                                      </span>
                                    ))}
                                    {modelsToShow.length > 3 && (
                                      <span className="px-1.5 py-0.5 text-[0.625rem] rounded-[var(--radius-sm)] bg-[var(--mc-subtle)] text-[var(--mc-muted)] font-mono">
                                        +{modelsToShow.length - 3}
                                      </span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className="text-[var(--mc-muted)]">{cred.provider}</span>
                          </td>
                          <td>
                            <span className={`tag-type ${cred.type === "managed" ? "tag-managed" : "tag-byo"}`}>
                              {cred.type === "managed" ? t.credentials.tag_managed : t.credentials.tag_byo}
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
                                          <path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2L12 2Z" fill={`url(#geminiGradient-${cred.id})`} />
                                          <defs>
                                            <linearGradient id={`geminiGradient-${cred.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                                              <stop offset="0%" stopColor="#1A73E8" />
                                              <stop offset="50%" stopColor="#8AB4F8" />
                                              <stop offset="100%" stopColor="#C68BFC" />
                                            </linearGradient>
                                          </defs>
                                        </svg>
                                      </div>
                                      <span className="font-semibold text-[var(--mc-text)] min-w-[38px] mr-0.5">Gemini:</span>
                                      {g5h !== null && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[var(--mc-muted)]">5h</span>
                                          <span className="font-mono font-bold min-w-[22px] text-right text-[var(--mc-text)]">{g5h}%</span>
                                          <div className="w-8 h-1 bg-[var(--mc-subtle)] rounded-full overflow-hidden border border-[var(--mc-border)]">
                                            <div className={`h-full ${g5h < 15 ? "bg-[var(--mc-danger)]" : g5h < 40 ? "bg-[var(--mc-warn)]" : "bg-[var(--mc-ok)]"}`} style={{ width: `${g5h}%` }} />
                                          </div>
                                        </div>
                                      )}
                                      {gW !== null && (
                                        <div className="flex items-center gap-1 ml-1">
                                          <span className="text-[var(--mc-muted)]">W</span>
                                          <span className="font-mono font-bold min-w-[22px] text-right text-[var(--mc-text)]">{gW}%</span>
                                          <div className="w-8 h-1 bg-[var(--mc-subtle)] rounded-full overflow-hidden border border-[var(--mc-border)]">
                                            <div className={`h-full ${gW < 15 ? "bg-[var(--mc-danger)]" : gW < 40 ? "bg-[var(--mc-warn)]" : "bg-[var(--mc-ok)]"}`} style={{ width: `${gW}%` }} />
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
                                          <path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" fill={`url(#anthropicGradient-${cred.id})`} />
                                          <path d="M17 11L18 14L21 15L18 16L17 19L16 16L13 15L16 14L17 11Z" fill={`url(#anthropicGradient-${cred.id})`} />
                                          <defs>
                                            <linearGradient id={`anthropicGradient-${cred.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                                              <stop offset="0%" stopColor="#F59E0B" />
                                              <stop offset="100%" stopColor="#D97706" />
                                            </linearGradient>
                                          </defs>
                                        </svg>
                                      </div>
                                      <span className="font-semibold text-[var(--mc-text)] min-w-[38px] mr-0.5">Other:</span>
                                      {c5h !== null && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[var(--mc-muted)]">5h</span>
                                          <span className="font-mono font-bold min-w-[22px] text-right text-[var(--mc-text)]">{c5h}%</span>
                                          <div className="w-8 h-1 bg-[var(--mc-subtle)] rounded-full overflow-hidden border border-[var(--mc-border)]">
                                            <div className={`h-full ${c5h < 15 ? "bg-[var(--mc-danger)]" : c5h < 40 ? "bg-[var(--mc-warn)]" : "bg-[var(--mc-ok)]"}`} style={{ width: `${c5h}%` }} />
                                          </div>
                                        </div>
                                      )}
                                      {cW !== null && (
                                        <div className="flex items-center gap-1 ml-1">
                                          <span className="text-[var(--mc-muted)]">W</span>
                                          <span className="font-mono font-bold min-w-[22px] text-right text-[var(--mc-text)]">{cW}%</span>
                                          <div className="w-8 h-1 bg-[var(--mc-subtle)] rounded-full overflow-hidden border border-[var(--mc-border)]">
                                            <div className={`h-full ${cW < 15 ? "bg-[var(--mc-danger)]" : cW < 40 ? "bg-[var(--mc-warn)]" : "bg-[var(--mc-ok)]"}`} style={{ width: `${cW}%` }} />
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}
                              </div>
                            ) : remaining !== null && cred.quotaTotalTokens !== null && cred.quotaTotalTokens > 0 ? (
                              <div className="flex flex-col gap-1 w-full max-w-[12rem]" onClick={(e) => e.stopPropagation()}>
                                <div className="flex justify-between items-center gap-2 text-[0.6875rem] font-mono text-[var(--mc-muted)]">
                                  <span>{t.credentials.lbl_remaining}</span>
                                  <span className="whitespace-nowrap font-bold text-[var(--mc-text)]">{Math.round(pct)}%</span>
                                </div>
                                <div className="w-full h-1 bg-[var(--mc-subtle)] rounded-full overflow-hidden border border-[var(--mc-border)]">
                                  <div
                                    className={`h-full ${
                                      pct < 15
                                        ? "bg-[var(--mc-danger)]"
                                        : pct < 40
                                        ? "bg-[var(--mc-warn)]"
                                        : "bg-[var(--mc-ok)]"
                                    }`}
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                              </div>
                            ) : (
                              <span className="text-[var(--mc-muted)]">—</span>
                            )}
                          </td>
                          <td>
                            <span className={`mc-pill is-${cred.status}`}>
                              <span className="mc-dot" />
                              {t.common[cred.status as keyof typeof t.common] || cred.status}
                            </span>
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr className="bg-[var(--mc-subtle)]">
                            <td colSpan={5} className="p-0 border-b border-[var(--mc-border)]">
                              <div
                                className="p-6 flex flex-col gap-6 animate-in slide-in-from-top duration-300"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                                  <div className="md:col-span-3 bg-[var(--bg-app)] border border-[var(--border)] rounded-[var(--radius-md)] p-5 flex flex-col gap-4">
                                    <h5 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">
                                      {t.credentials.lbl_controls}
                                    </h5>
                                    
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                      <div className="flex flex-col gap-1.5">
                                        <label htmlFor={`prio-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                          {t.credentials.lbl_priority}
                                        </label>
                                        <input
                                          id={`prio-${cred.id}`}
                                          type="number"
                                          value={priorityVal}
                                          onChange={(e) =>
                                            setEditPriorities((prev) => ({
                                              ...prev,
                                              [cred.id]: Number(e.target.value),
                                            }))
                                          }
                                          className="premium-input outline-none"
                                          min={1}
                                        />
                                      </div>
                                      
                                      <div className="flex flex-col gap-1.5">
                                        <label htmlFor={`quota-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                          {language === "en" ? "Token Quota" : "Квота токенов"}
                                        </label>
                                        <input
                                          id={`quota-${cred.id}`}
                                          type="number"
                                          value={editQuotas[cred.id] ?? ""}
                                          onChange={(e) =>
                                            setEditQuotas((prev) => ({
                                              ...prev,
                                              [cred.id]: e.target.value ? Number(e.target.value) : null,
                                            }))
                                          }
                                          placeholder="Unlimited"
                                          className="premium-input outline-none"
                                        />
                                      </div>

                                      {cred.type !== "managed" && (
                                        <div className="flex flex-col gap-1.5">
                                          <label htmlFor={`models-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                            {t.credentials.lbl_models_short}
                                          </label>
                                          <input
                                            id={`models-${cred.id}`}
                                            type="text"
                                            value={editModels[cred.id] ?? ""}
                                            onChange={(e) =>
                                              setEditModels((prev) => ({
                                                ...prev,
                                                [cred.id]: e.target.value,
                                              }))
                                            }
                                            placeholder="gemini-1.5-pro, gemini-1.5-flash"
                                            className="premium-input outline-none"
                                          />
                                        </div>
                                      )}
                                    </div>

                                    <details className="group">
                                      <summary className="text-xs font-semibold text-[var(--text-muted)] cursor-pointer hover:text-[var(--text-main)] select-none flex items-center gap-1 py-2 outline-none">
                                        <ChevronRight className="w-3.5 h-3.5 transition-transform group-open:rotate-90" />
                                        {t.credentials.lbl_advanced}
                                      </summary>
                                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
                                        <div className="flex flex-col gap-1.5">
                                          <label htmlFor={`weight-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                            {t.credentials.lbl_weight}
                                          </label>
                                          <input
                                            id={`weight-${cred.id}`}
                                            type="number"
                                            value={weightVal}
                                            onChange={(e) =>
                                              setEditWeights((prev) => ({
                                                ...prev,
                                                [cred.id]: Number(e.target.value),
                                              }))
                                            }
                                            className="premium-input outline-none"
                                            min={1}
                                          />
                                        </div>
                                        
                                        <div className="flex flex-col gap-1.5">
                                          <label htmlFor={`concurrency-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                            {t.credentials.lbl_concurrency}
                                          </label>
                                          <input
                                            id={`concurrency-${cred.id}`}
                                            type="number"
                                            value={concurrencyVal}
                                            onChange={(e) =>
                                              setEditConcurrencies((prev) => ({
                                                ...prev,
                                                [cred.id]: Number(e.target.value),
                                              }))
                                            }
                                            className="premium-input outline-none"
                                            min={0}
                                          />
                                        </div>

                                        <div className="flex flex-col gap-1.5">
                                          <label htmlFor={`window-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                            {t.credentials.lbl_reset_window_short}
                                          </label>
                                          <input
                                            id={`window-${cred.id}`}
                                            type="number"
                                            value={editWindows[cred.id] ?? ""}
                                            onChange={(e) =>
                                              setEditWindows((prev) => ({
                                                ...prev,
                                                [cred.id]: e.target.value ? Number(e.target.value) : null,
                                              }))
                                            }
                                            placeholder="e.g. 86400"
                                            className="premium-input outline-none"
                                          />
                                        </div>

                                        <div className="flex flex-col gap-1.5">
                                          <label htmlFor={`status-${cred.id}`} className="text-xs font-semibold text-[var(--text-muted)]">
                                            {t.credentials.lbl_manual_state}
                                          </label>
                                          <select
                                            id={`status-${cred.id}`}
                                            value={cred.status}
                                            onChange={(e) =>
                                              toggleCredentialStatus(
                                                cred.id,
                                                e.target.value as Credential["status"]
                                              )
                                            }
                                            className="premium-select outline-none w-full"
                                          >
                                            <option value="active">{t.common.active}</option>
                                            <option value="cooldown">{t.common.cooldown}</option>
                                            <option value="exhausted">{t.common.exhausted}</option>
                                            <option value="degraded">{t.common.degraded}</option>
                                            <option value="error">{t.common.error}</option>
                                            <option value="reauth_required">{t.common.reauth_required}</option>
                                            <option value="disabled">{t.common.disabled}</option>
                                          </select>
                                        </div>
                                      </div>
                                    </details>

                                    <div className="flex flex-wrap gap-2 mt-2">
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleSaveChanges(cred.id);
                                        }}
                                        className="px-4 py-2 bg-[var(--primary)] hover:bg-[var(--primary-hover)] text-white text-xs font-bold rounded-[var(--radius-sm)] transition-colors flex items-center gap-1"
                                      >
                                        <Check className="w-3.5 h-3.5" />
                                        {t.credentials.btn_save_settings}
                                      </button>
                                      {cred.type === "managed" && (
                                        <button
                                          type="button"
                                          onClick={async (e) => {
                                            e.stopPropagation();
                                            await refreshCredentialQuota(cred.id);
                                          }}
                                          className="px-4 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] hover:bg-[var(--bg-panel-hover)] hover:text-[var(--primary)] rounded-[var(--radius-sm)] transition-colors flex items-center gap-1 text-[var(--text-main)] font-semibold text-xs"
                                        >
                                          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                                          </svg>
                                          {t.common.refresh}
                                        </button>
                                      )}
                                      <button
                                        type="button"
                                        onClick={async (e) => {
                                          e.stopPropagation();
                                          if (window.confirm(t.credentials.confirm_delete)) {
                                            await deleteCredential(cred.id);
                                          }
                                        }}
                                        className="px-4 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] hover:bg-[var(--color-danger)] hover:text-white rounded-[var(--radius-sm)] transition-colors flex items-center gap-1 text-[var(--text-main)] text-xs"
                                      >
                                        <Trash2 className="w-3.5 h-3.5" />
                                        {t.credentials.btn_delete}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          toggleRow(cred.id);
                                        }}
                                        className="px-4 py-2 border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-xs font-bold rounded-[var(--radius-sm)] transition-colors"
                                      >
                                        {t.credentials.btn_close}
                                      </button>
                                    </div>
                                  </div>

                                  <div className="flex flex-col gap-4">
                                    <div className="flex-1 bg-[var(--bg-app)] border border-[var(--border)] rounded-[var(--radius-md)] p-4 flex flex-col justify-between">
                                      <div className="flex items-center gap-1 text-[var(--text-muted)] font-bold text-xs uppercase mb-2">
                                        <ShieldAlert className="w-3.5 h-3.5 text-[var(--primary)]" />
                                        <span>{t.credentials.lbl_json_spec}</span>
                                      </div>
                                      <pre className="text-[0.625rem] text-[var(--text-muted)] overflow-auto max-h-32 font-mono leading-relaxed bg-[color:rgba(0,0,0,0.15)] p-2 rounded border border-[var(--border)] flex-1">
                                        {cred.details}
                                      </pre>
                                    </div>
                                  </div>
                                </div>

                                <div className="mt-5 flex flex-col gap-3">
                                  {(cred.loadError || cred.quotaError) && (
                                    <div className="p-3 bg-[color:rgba(239,68,68,0.1)] border border-[color:rgba(239,68,68,0.2)] rounded-[var(--radius-md)] flex items-start gap-2.5 text-xs text-[var(--color-danger)]">
                                      <ShieldAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />
                                      <div className="flex flex-col gap-1">
                                        {cred.loadError && (
                                          <div>
                                            <span className="font-bold">Load Error:</span> {renderErrorWithLinks(cred.loadError)}
                                          </div>
                                        )}
                                        {cred.quotaError && (
                                          <div>
                                            <span className="font-bold">Quota Error:</span> {renderErrorWithLinks(cred.quotaError)}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}

                                   {/* Недельные и 5-часовые лимиты Antigravity */}
                                   {cred.modelQuotas && (cred.modelQuotas["gemini-weekly"] !== undefined || cred.modelQuotas["3p-weekly"] !== undefined) && (
                                     <div className="flex flex-col gap-3 p-3.5 bg-[var(--bg-app)] border border-[var(--border)] rounded-[var(--radius-md)]">
                                       <div className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider">
                                         {t.credentials.lbl_usage_limits}
                                       </div>
                                       
                                       {/* Группа Gemini */}
                                       {cred.modelQuotas["gemini-weekly"] !== undefined && (
                                         <div className="flex flex-col gap-2 p-2.5 bg-[var(--bg-subtle)] rounded-[var(--radius-sm)] border border-[var(--border)]">
                                           <div className="text-xs font-bold text-[var(--text-main)] flex items-center gap-1.5">
                                             <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                                               <path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2L12 2Z" fill={`url(#geminiGradientExpanded-${cred.id})`} />
                                               <defs>
                                                 <linearGradient id={`geminiGradientExpanded-${cred.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                                                   <stop offset="0%" stopColor="#1A73E8" />
                                                   <stop offset="50%" stopColor="#8AB4F8" />
                                                   <stop offset="100%" stopColor="#C68BFC" />
                                                 </linearGradient>
                                               </defs>
                                             </svg>
                                             <span>Gemini Models (Flash, Pro)</span>
                                           </div>
                                           <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-1">
                                             {/* 5h */}
                                             {cred.modelQuotas["gemini-5h"] !== undefined && (() => {
                                               const val = cred.modelQuotas["gemini-5h"];
                                               const pct = Math.round(val * 100);
                                               const reset = cred.modelQuotas["gemini-5h:reset"] as unknown as string | null;
                                               const countdown = getResetCountdown(reset);
                                               return (
                                                 <div className="flex flex-col gap-1.5">
                                                   <div className="text-[10px] text-[var(--text-muted)] font-semibold flex justify-between leading-none">
                                                     <span>5-Hour Limit</span>
                                                     <span className="font-bold text-[var(--text-main)]">{pct}%</span>
                                                   </div>
                                                   <div className="w-full h-1.5 bg-[var(--bg-app)] rounded-full overflow-hidden border border-[var(--border)]">
                                                     <div className={`h-full ${pct < 15 ? "bg-[var(--color-danger)]" : pct < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${pct}%` }} />
                                                   </div>
                                                   {countdown && <span className="text-[9px] text-[var(--text-muted)] font-medium leading-none">{countdown}</span>}
                                                 </div>
                                               );
                                             })()}
                                             {/* Weekly */}
                                             {cred.modelQuotas["gemini-weekly"] !== undefined && (() => {
                                               const val = cred.modelQuotas["gemini-weekly"];
                                               const pct = Math.round(val * 100);
                                               const reset = cred.modelQuotas["gemini-weekly:reset"] as unknown as string | null;
                                               const countdown = getResetCountdown(reset);
                                               return (
                                                 <div className="flex flex-col gap-1.5">
                                                   <div className="text-[10px] text-[var(--text-muted)] font-semibold flex justify-between leading-none">
                                                     <span>Weekly Limit</span>
                                                     <span className="font-bold text-[var(--text-main)]">{pct}%</span>
                                                   </div>
                                                   <div className="w-full h-1.5 bg-[var(--bg-app)] rounded-full overflow-hidden border border-[var(--border)]">
                                                     <div className={`h-full ${pct < 15 ? "bg-[var(--color-danger)]" : pct < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${pct}%` }} />
                                                   </div>
                                                   {countdown && <span className="text-[9px] text-[var(--text-muted)] font-medium leading-none">{countdown}</span>}
                                                 </div>
                                               );
                                             })()}
                                           </div>
                                         </div>
                                       )}

                                       {/* Группа Claude & GPT */}
                                       {cred.modelQuotas["3p-weekly"] !== undefined && (
                                         <div className="flex flex-col gap-2 p-2.5 bg-[var(--bg-subtle)] rounded-[var(--radius-sm)] border border-[var(--border)]">
                                           <div className="text-xs font-bold text-[var(--text-main)] flex items-center gap-1.5">
                                             <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                                               <path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" fill={`url(#anthropicGradientExpanded-${cred.id})`} />
                                               <path d="M17 11L18 14L21 15L18 16L17 19L16 16L13 15L16 14L17 11Z" fill={`url(#anthropicGradientExpanded-${cred.id})`} />
                                               <defs>
                                                 <linearGradient id={`anthropicGradientExpanded-${cred.id}`} x1="0%" y1="0%" x2="100%" y2="100%">
                                                   <stop offset="0%" stopColor="#F59E0B" />
                                                   <stop offset="100%" stopColor="#D97706" />
                                                 </linearGradient>
                                               </defs>
                                             </svg>
                                             <span>Claude & GPT Models (Opus, Sonnet, GPT-OSS)</span>
                                           </div>
                                           <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-1">
                                             {/* 5h */}
                                             {cred.modelQuotas["3p-5h"] !== undefined && (() => {
                                               const val = cred.modelQuotas["3p-5h"];
                                               const pct = Math.round(val * 100);
                                               const reset = cred.modelQuotas["3p-5h:reset"] as unknown as string | null;
                                               const countdown = getResetCountdown(reset);
                                               return (
                                                 <div className="flex flex-col gap-1.5">
                                                   <div className="text-[10px] text-[var(--text-muted)] font-semibold flex justify-between leading-none">
                                                     <span>5-Hour Limit</span>
                                                     <span className="font-bold text-[var(--text-main)]">{pct}%</span>
                                                   </div>
                                                   <div className="w-full h-1.5 bg-[var(--bg-app)] rounded-full overflow-hidden border border-[var(--border)]">
                                                     <div className={`h-full ${pct < 15 ? "bg-[var(--color-danger)]" : pct < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${pct}%` }} />
                                                   </div>
                                                   {countdown && <span className="text-[9px] text-[var(--text-muted)] font-medium leading-none">{countdown}</span>}
                                                 </div>
                                               );
                                             })()}
                                             {/* Weekly */}
                                             {cred.modelQuotas["3p-weekly"] !== undefined && (() => {
                                               const val = cred.modelQuotas["3p-weekly"];
                                               const pct = Math.round(val * 100);
                                               const reset = cred.modelQuotas["3p-weekly:reset"] as unknown as string | null;
                                               const countdown = getResetCountdown(reset);
                                               return (
                                                 <div className="flex flex-col gap-1.5">
                                                   <div className="text-[10px] text-[var(--text-muted)] font-semibold flex justify-between leading-none">
                                                     <span>Weekly Limit</span>
                                                     <span className="font-bold text-[var(--text-main)]">{pct}%</span>
                                                   </div>
                                                   <div className="w-full h-1.5 bg-[var(--bg-app)] rounded-full overflow-hidden border border-[var(--border)]">
                                                     <div className={`h-full ${pct < 15 ? "bg-[var(--color-danger)]" : pct < 40 ? "bg-[var(--color-warning)]" : "bg-[var(--color-success)]"}`} style={{ width: `${pct}%` }} />
                                                   </div>
                                                   {countdown && <span className="text-[9px] text-[var(--text-muted)] font-medium leading-none">{countdown}</span>}
                                                 </div>
                                               );
                                             })()}
                                           </div>
                                         </div>
                                       )}
                                     </div>
                                   )}

                                  {cred.type !== "managed" && modelsToShow && modelsToShow.length > 0 && (
                                    <button
                                      type="button"
                                      onClick={() => setExpandedModels(prev => ({ ...prev, [cred.id]: !prev[cred.id] }))}
                                      className="w-full py-2 bg-[var(--bg-subtle)] border border-[var(--border)] hover:bg-[var(--bg-panel-hover)] text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--text-main)] rounded-[var(--radius-md)] flex items-center justify-center gap-1.5 transition-colors focus-ring"
                                    >
                                      <ChevronRight
                                        className={`w-3.5 h-3.5 transition-transform ${expandedModels[cred.id] ? "rotate-90 text-[var(--primary)]" : ""}`}
                                      />
                                      {expandedModels[cred.id]
                                        ? `${t.credentials.btn_hide_model_quotas} (${modelsToShow.length})`
                                        : `${t.credentials.btn_show_model_quotas} (${modelsToShow.length})`}
                                    </button>
                                  )}

                                  {cred.type !== "managed" && expandedModels[cred.id] && modelsToShow && modelsToShow.length > 0 && (
                                    <div className="flex flex-col gap-4 mt-2 p-4 bg-[var(--bg-app)] border border-[var(--border)] rounded-[var(--radius-md)]">
                                      {modelsToShow.map((model) => {
                                        let pctModel = 100;
                                        if (cred.status === "error") {
                                          pctModel = 0;
                                        } else if (cred.modelQuotas && cred.modelQuotas[model] !== undefined) {
                                          const val = cred.modelQuotas[model];
                                          pctModel = val <= 1.0 ? Math.round(val * 100) : Math.round(val);
                                        } else if (cred.quotaTotalTokens !== null && cred.quotaTotalTokens > 0) {
                                          const rem = cred.quotaTotalTokens - cred.quotaUsedTokens;
                                          pctModel = Math.round((Math.max(0, rem) / cred.quotaTotalTokens) * 100);
                                        }

                                        let barColorClass = "bg-[var(--color-success)]";
                                        let textPercentClass = "text-[var(--color-success)]";
                                        if (pctModel < 15) {
                                          barColorClass = "bg-[var(--color-danger)]";
                                          textPercentClass = "text-[var(--color-danger)]";
                                        } else if (pctModel < 40) {
                                          barColorClass = "bg-[var(--color-warning)]";
                                          textPercentClass = "text-[var(--color-warning)]";
                                        }

                                        const countdown = getResetCountdown(cred.resetAt);

                                        return (
                                          <div
                                            key={model}
                                            className="flex items-center justify-between text-sm py-1.5 border-b border-[var(--border)] border-dashed last:border-0"
                                          >
                                            <span className="font-semibold text-[var(--text-main)]">
                                              {model}
                                            </span>
                                            <div className="flex items-center gap-4">
                                              <span className={`text-base font-bold ${textPercentClass}`}>
                                                {pctModel}%
                                              </span>
                                              <div className="flex flex-col gap-1 w-28 items-end">
                                                {countdown && (
                                                  <span className="text-[0.625rem] text-[var(--text-muted)] font-medium leading-none mb-0.5">
                                                    {countdown}
                                                  </span>
                                                )}
                                                <div className="w-full h-1 bg-[var(--bg-subtle)] rounded-full overflow-hidden border border-[var(--border)]">
                                                  <div
                                                    className={`h-full ${barColorClass}`}
                                                    style={{ width: `${pctModel}%` }}
                                                  />
                                                </div>
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}

                                  {cred.type !== "managed" && (!modelsToShow || modelsToShow.length === 0) && (
                                    <div className="text-xs text-[var(--text-muted)] italic">
                                      {t.credentials.lbl_no_models}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
