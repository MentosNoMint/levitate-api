import React from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { translations } from "@/store/translations";
import { Sparkles, ArrowRight } from "lucide-react";

export default function LoginScreen() {
  const { language, setLanguage, googleOauthConfigured } = useDashboardStore();
  const t = translations[language];

  const getApiUrl = (): string => {
    if (typeof window !== "undefined") {
      return window.location.protocol + "//" + window.location.hostname + ":8000";
    }
    return "http://localhost:8000";
  };

  return (
    <div className="min-h-screen bg-[var(--bg-app)] text-[var(--text-main)] flex flex-col justify-between p-6 relative overflow-hidden font-sans">
      {/* Background ambient glows */}
      <div className="absolute top-[-20%] left-[-10%] w-[50vw] h-[50vw] rounded-full bg-gradient-to-tr from-[var(--primary)] to-orange-950/20 blur-[120px] opacity-30 pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40vw] h-[40vw] rounded-full bg-gradient-to-br from-orange-900/10 to-red-950/10 blur-[100px] opacity-20 pointer-events-none" />

      {/* Header with language switcher */}
      <header className="flex justify-between items-center w-full max-w-7xl mx-auto z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-[var(--radius-sm)] flex items-center justify-center shadow-lg shadow-orange-500/20" style={{ backgroundImage: "var(--branding-gradient)" }}>
            <div className="w-3.5 h-3.5 bg-white/90 rounded-[0.125rem]" />
          </div>
          <span className="font-semibold text-lg tracking-tight bg-gradient-to-r from-[var(--text-main)] to-[var(--text-muted)] bg-clip-text text-transparent">
            Levitate API
          </span>
        </div>

        <div className="flex items-center gap-1 bg-[var(--bg-subtle)] border border-[var(--border)] p-1 rounded-md">
          <button
            onClick={() => setLanguage("en")}
            className={`px-2.5 py-1 text-xs font-semibold rounded transition-all duration-200 ${
              language === "en"
                ? "bg-[var(--primary)] text-white shadow-md shadow-indigo-500/25"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
            }`}
          >
            EN
          </button>
          <button
            onClick={() => setLanguage("ru")}
            className={`px-2.5 py-1 text-xs font-semibold rounded transition-all duration-200 ${
              language === "ru"
                ? "bg-[var(--primary)] text-white shadow-md shadow-indigo-500/25"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
            }`}
          >
            RU
          </button>
        </div>
      </header>

      {/* Main card */}
      <main className="flex-1 flex items-center justify-center z-10 py-12">
        <div className="w-full max-w-[26rem] bg-[var(--bg-panel)]/40 backdrop-blur-xl border border-[var(--border)] rounded-[var(--radius-lg)] p-8 shadow-2xl relative group">
          {/* Top subtle highlight line */}
          <div className="absolute top-0 inset-x-0 h-[0.0625rem] bg-gradient-to-r from-transparent via-[var(--primary)]/50 to-transparent opacity-80" />

          <div className="flex flex-col items-center text-center gap-6">
            <div className="w-12 h-12 rounded-full bg-[var(--primary-dim)] border border-[var(--border)] flex items-center justify-center text-[var(--primary)] animate-pulse">
              <Sparkles className="w-5 h-5" />
            </div>

            <div className="flex flex-col gap-2">
              <h1 className="text-xl font-bold tracking-tight text-[var(--text-main)]">
                {t.login.title}
              </h1>
              <p className="text-xs text-[var(--text-muted)] leading-relaxed max-w-[20rem] mx-auto">
                {t.login.desc}
              </p>
            </div>

            <div className="w-full flex flex-col gap-3 mt-4">
              {googleOauthConfigured ? (
                <a
                  href={`${getApiUrl()}/admin/auth/login`}
                  className="w-full flex items-center justify-center gap-3 py-3 px-4 bg-white hover:bg-neutral-100 text-neutral-900 text-sm font-semibold rounded-[var(--radius-md)] transition-all duration-200 shadow-lg shadow-white/5 active:scale-[0.98] focus-ring"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24">
                    <path
                      fill="#EA4335"
                      d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114-3.555 0-6.438-2.883-6.438-6.438 0-3.555 2.883-6.438 6.438-6.438 1.547 0 2.956.545 4.062 1.455l3.087-3.087C19.014 1.954 15.823 1 12.24 1 5.922 1 1 5.922 1 12.24s4.922 11.24 11.24 11.24c6.318 0 11.24-4.922 11.24-11.24 0-.682-.068-1.364-.205-1.955H12.24Z"
                    />
                  </svg>
                  {t.login.btn_google}
                </a>
              ) : (
                <div className="w-full flex flex-col gap-2 p-3 bg-indigo-500/5 border border-[var(--primary)]/20 rounded-[var(--radius-md)] text-center">
                  <span className="text-[10px] text-[var(--primary)] font-semibold uppercase tracking-wider">
                    {t.login.dev_mode_title}
                  </span>
                  <span className="text-[11px] text-[var(--text-muted)]">
                    {t.login.dev_mode_desc}
                  </span>
                </div>
              )}

              {/* Developer login option */}
              <a
                href={`${getApiUrl()}/admin/auth/mock`}
                className="w-full flex items-center justify-between py-3 px-4 bg-[var(--bg-subtle)] hover:bg-[var(--bg-panel-hover)] border border-[var(--border)] text-[var(--text-main)] text-sm font-semibold rounded-[var(--radius-md)] transition-all duration-200 hover:border-[var(--border-active)] active:scale-[0.98] group/btn focus-ring"
              >
                <span>{t.login.btn_mock}</span>
                <ArrowRight className="w-4 h-4 text-[var(--text-dark)] group-hover/btn:translate-x-1 group-hover/btn:text-[var(--primary)] transition-all" />
              </a>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="text-center w-full z-10">
        <span className="text-[11px] text-[var(--text-dark)] uppercase tracking-wider font-semibold">
          {t.login.footer}
        </span>
      </footer>
    </div>
  );
}
