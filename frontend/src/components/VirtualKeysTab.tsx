import React, { useState } from "react";
import { useDashboardStore, VirtualKey } from "@/store/dashboardStore";
import { Plus, ToggleLeft, ToggleRight, Edit2, Check, X, Shield, Copy } from "lucide-react";
import { translations } from "@/store/translations";
import { Modal } from "./Modal";

export default function VirtualKeysTab() {
  const {
    language,
    virtualKeys,
    addVirtualKey,
    toggleVirtualKeyStatus,
    updateVirtualKeyBudget,
    lastGeneratedKey,
    clearGeneratedKey,
  } = useDashboardStore();
  const t = translations[language];

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingKeyId, setEditingKeyId] = useState<string | null>(null);

  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyMonthlyLimit, setNewKeyMonthlyLimit] = useState(5000000);
  const [newKeyRpmLimit, setNewKeyRpmLimit] = useState(1200);
  const [newKeyPriority, setNewKeyPriority] = useState<VirtualKey["priority"]>("Medium");

  const [editMonthlyLimit, setEditMonthlyLimit] = useState(0);
  const [editRpmLimit, setEditRpmLimit] = useState(0);

  const [copied, setCopied] = useState(false);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    await addVirtualKey(newKeyName, newKeyMonthlyLimit, newKeyRpmLimit, newKeyPriority);
    setNewKeyName("");
    setNewKeyMonthlyLimit(5000000);
    setNewKeyRpmLimit(1200);
    setNewKeyPriority("Medium");
  };

  const handleCloseModal = () => {
    setShowCreateForm(false);
    clearGeneratedKey();
  };

  const handleCopy = () => {
    if (lastGeneratedKey) {
      navigator.clipboard.writeText(lastGeneratedKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const startEditing = (key: VirtualKey) => {
    setEditingKeyId(key.id);
    setEditMonthlyLimit(key.monthlyLimit);
    setEditRpmLimit(key.rpmLimit);
  };

  const saveEditing = (id: string) => {
    updateVirtualKeyBudget(id, editMonthlyLimit, editRpmLimit);
    setEditingKeyId(null);
  };

  const cancelEditing = () => {
    setEditingKeyId(null);
  };

  return (
    <div className="overview-mc flex flex-col gap-6" id="view-keys">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[var(--text-main)]">
            {t.keys.title}
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.keys.desc}
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="primary-action-btn focus-ring flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          {t.keys.btn_create}
        </button>
      </div>

      <Modal
        open={showCreateForm}
        onClose={handleCloseModal}
        title={lastGeneratedKey ? t.keys.created_title : t.keys.form_title}
      >
        {lastGeneratedKey ? (
          <div className="flex flex-col gap-4">
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              {t.keys.created_desc}
            </p>
            <div className="flex items-center gap-2 bg-[var(--bg-subtle)] border border-[var(--border)] p-2 rounded-[var(--radius-md)]">
              <span className="font-mono text-xs text-[var(--text-main)] break-all select-all flex-1">
                {lastGeneratedKey}
              </span>
              <button
                type="button"
                onClick={handleCopy}
                className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] rounded-md transition-colors shrink-0 focus-ring"
                aria-label={t.keys.btn_copy}
              >
                {copied ? (
                  <Check className="w-4 h-4 text-[var(--color-success)]" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-[var(--border)]">
              <button
                type="button"
                onClick={handleCloseModal}
                className="primary-action-btn focus-ring"
              >
                {t.keys.btn_done}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleCreateKey} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="key-name" className="text-xs font-semibold text-[var(--text-muted)]">
                {t.keys.form_name}
              </label>
              <input
                id="key-name"
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="sk-lev-prod-core"
                className="premium-input outline-none"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="key-priority" className="text-xs font-semibold text-[var(--text-muted)]">
                {t.keys.form_priority}
              </label>
              <select
                id="key-priority"
                value={newKeyPriority}
                onChange={(e) => setNewKeyPriority(e.target.value as VirtualKey["priority"])}
                className="premium-select outline-none"
              >
                <option value="High">{t.keys.high_priority}</option>
                <option value="Medium">{t.keys.medium_priority}</option>
                <option value="Low">{t.keys.low_priority}</option>
              </select>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="key-monthly-limit" className="text-xs font-semibold text-[var(--text-muted)]">
                  {t.keys.form_quota}
                </label>
                <input
                  id="key-monthly-limit"
                  type="number"
                  value={newKeyMonthlyLimit}
                  onChange={(e) => setNewKeyMonthlyLimit(Number(e.target.value))}
                  className="premium-input outline-none"
                  required
                  min={1}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="key-rpm-limit" className="text-xs font-semibold text-[var(--text-muted)]">
                  {t.keys.form_rpm}
                </label>
                <input
                  id="key-rpm-limit"
                  type="number"
                  value={newKeyRpmLimit}
                  onChange={(e) => setNewKeyRpmLimit(Number(e.target.value))}
                  className="premium-input outline-none"
                  required
                  min={1}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-[var(--border)]">
              <button
                type="button"
                onClick={handleCloseModal}
                className="px-4 py-2 border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] text-sm font-semibold rounded-[var(--radius-md)] transition-colors"
              >
                {t.keys.btn_cancel}
              </button>
              <button type="submit" className="primary-action-btn focus-ring">
                {t.keys.form_btn}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <div className="mc-panel">
        <table className="mc-table">
          <thead>
            <tr>
              <th className="w-[30%]">{t.keys.col_name}</th>
              <th className="w-[15%]">{t.keys.col_status}</th>
              <th className="w-[25%]">{t.keys.col_usage}</th>
              <th className="w-[12%]">{t.keys.col_rpm}</th>
              <th className="w-[10%]">{t.keys.col_priority}</th>
              <th className="w-[8%] text-right">{t.keys.col_actions}</th>
            </tr>
          </thead>
          <tbody>
            {virtualKeys.map((key) => {
              const usagePercent = key.monthlyLimit > 0 ? (key.monthlyUsage / key.monthlyLimit) * 100 : 0;
              const isEditing = editingKeyId === key.id;

              return (
                <tr key={key.id}>
                  <td>
                    <div className="flex flex-col gap-1">
                      <span className="font-semibold text-[var(--mc-text)]">
                        {t.mock[key.name as keyof typeof t.mock] || key.name}
                      </span>
                      <span className="text-[var(--mc-muted)] text-xs font-mono select-all truncate max-w-[12rem]">
                        {key.key}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={`mc-pill ${
                      key.status === "active"
                        ? "is-active"
                        : key.status === "warning"
                        ? "is-cooldown"
                        : "is-exhausted"
                    }`}>
                      <span className="mc-dot" />
                      {t.common[key.status]}
                    </span>
                  </td>
                  <td>
                    <div className="flex flex-col gap-1 w-full max-w-[14rem]" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-between items-center gap-2 text-[0.6875rem] font-mono text-[var(--mc-muted)]">
                        <span>{Math.round(usagePercent)}%</span>
                        <span className="whitespace-nowrap">
                          {isEditing ? (
                            <span className="flex items-center gap-1">
                              <input
                                type="number"
                                value={editMonthlyLimit}
                                onChange={(e) => setEditMonthlyLimit(Number(e.target.value))}
                                className="w-24 premium-input px-1.5 py-0.5 text-xs outline-none"
                                min={1}
                              />
                              {t.keys.tokens_suffix}
                            </span>
                          ) : (
                            `${(key.monthlyUsage / 1000000).toFixed(2)}M / ${(
                              key.monthlyLimit / 1000000
                            ).toFixed(1)}M ${t.keys.tokens_suffix}`
                          )}
                        </span>
                      </div>
                      <div className="w-full h-1 bg-[var(--mc-subtle)] rounded-full overflow-hidden border border-[var(--mc-border)]">
                        <div
                          className={`h-full ${
                            usagePercent >= 95
                              ? "bg-[var(--mc-danger)]"
                              : usagePercent >= 80
                              ? "bg-[var(--mc-warn)]"
                              : "bg-[var(--mc-ok)]"
                          }`}
                          style={{ width: `${Math.min(usagePercent, 100)}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="text-[var(--mc-muted)] font-mono">
                    {isEditing ? (
                      <input
                        type="number"
                        value={editRpmLimit}
                        onChange={(e) => setEditRpmLimit(Number(e.target.value))}
                        className="w-20 premium-input px-1.5 py-0.5 text-xs outline-none"
                        min={1}
                      />
                    ) : (
                      `${key.rpmLimit.toLocaleString()} RPM`
                    )}
                  </td>
                  <td>
                    <span className="flex items-center gap-1 text-[var(--mc-muted)] text-sm">
                      <Shield className="w-3.5 h-3.5" />
                      {t.common[key.priority.toLowerCase() as "high" | "medium" | "low"]}
                    </span>
                  </td>
                  <td className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => saveEditing(key.id)}
                            className="p-2 text-[var(--color-success)] hover:bg-[var(--bg-panel-hover)] rounded-md focus-ring"
                            aria-label={t.keys.aria_save}
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={cancelEditing}
                            className="p-2 text-[var(--color-danger)] hover:bg-[var(--bg-panel-hover)] rounded-md focus-ring"
                            aria-label={t.keys.aria_cancel}
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEditing(key)}
                            className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] rounded-md focus-ring"
                            aria-label={t.keys.aria_edit}
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => toggleVirtualKeyStatus(key.id)}
                            className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] rounded-md focus-ring"
                            aria-label={key.status === "active" ? t.keys.aria_pause : t.keys.aria_resume}
                          >
                            {key.status === "active" ? (
                              <ToggleRight className="w-6 h-6 text-[var(--primary)]" />
                            ) : (
                              <ToggleLeft className="w-6 h-6" />
                            )}
                          </button>
                        </>
                      )}
                    </div>
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
