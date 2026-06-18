import React, { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { LayoutDashboard, Key, Shield, FileText, Menu, X, Sun, Moon } from "lucide-react";
import { translations } from "@/store/translations";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const { language, setLanguage, theme, setTheme, logout, user } = useDashboardStore();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const pathname = usePathname();

  const t = translations[language];

  const navItems = [
    { id: "overview", label: t.layout.overview, icon: LayoutDashboard, href: "/overview" },
    { id: "keys", label: t.layout.keys, icon: Key, href: "/keys" },
    { id: "credentials", label: t.layout.credentials, icon: Shield, href: "/credentials" },
    { id: "logs", label: t.layout.logs, icon: FileText, href: "/logs" },
  ];

  const getTabTitle = () => {
    if (pathname.startsWith("/overview")) return t.layout.overview_title;
    if (pathname.startsWith("/keys")) return t.layout.keys_title;
    if (pathname.startsWith("/credentials")) return t.layout.credentials_title;
    if (pathname.startsWith("/logs")) return t.layout.logs_title;
    return t.layout.overview_title;
  };

  return (
    <div className="flex h-screen max-h-screen flex-col md:flex-row bg-[var(--bg-app)] text-[var(--text-main)] overflow-hidden">
      <header className="md:hidden flex items-center justify-between px-6 py-4 bg-[var(--bg-panel)] border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-[var(--radius-sm)] flex items-center justify-center" style={{ backgroundImage: "var(--branding-gradient)" }}>
            <div className="w-3 h-3 bg-white/90 rounded-[0.125rem]" />
          </div>
          <span className="font-semibold text-lg tracking-tight">Levitate API</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)] rounded-[var(--radius-md)] transition-colors focus-ring"
            aria-label="Toggle theme"
          >
            {theme === "light" ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
          </button>
          <div className="flex items-center gap-1 bg-[var(--bg-subtle)] border border-[var(--border)] p-1 rounded-md">
            <button
              onClick={() => setLanguage("en")}
              className={`px-2 py-1 text-xs font-semibold rounded transition-colors ${
                language === "en"
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
              }`}
              aria-label="Switch to English"
            >
              EN
            </button>
            <button
              onClick={() => setLanguage("ru")}
              className={`px-2 py-1 text-xs font-semibold rounded transition-colors ${
                language === "ru"
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
              }`}
              aria-label="Переключить на русский"
            >
              RU
            </button>
          </div>
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] focus-ring rounded-[var(--radius-md)]"
            aria-label={isSidebarOpen ? "Close menu" : "Open menu"}
            aria-expanded={isSidebarOpen}
          >
            {isSidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </header>

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-[var(--bg-panel)] border-r border-[var(--border)] px-4 py-6 transform transition-transform duration-200 ease-in-out md:translate-x-0 md:static md:flex md:flex-col md:w-64 md:h-full flex-shrink-0 overflow-y-auto ${
          isSidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between mb-8 px-2">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-[var(--radius-sm)] flex items-center justify-center" style={{ backgroundImage: "var(--branding-gradient)" }}>
              <div className="w-3 h-3 bg-white/90 rounded-[0.125rem]" />
            </div>
            <span className="font-semibold text-lg tracking-tight">Levitate API</span>
          </div>
          <button
            onClick={() => setIsSidebarOpen(false)}
            className="md:hidden p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] rounded-[var(--radius-md)]"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav aria-label="Main Navigation" className="flex-1">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <li key={item.id}>
                  <Link
                    href={item.href}
                    onClick={() => setIsSidebarOpen(false)}
                    className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-[var(--radius-md)] transition-colors focus-ring ${
                      isActive
                        ? "text-[var(--primary)] bg-[var(--primary-dim)] font-semibold"
                        : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="mt-auto pt-4 border-t border-[var(--border)] flex flex-col gap-3">
          {user && (
            <div className="flex items-center gap-3 px-2 mb-2">
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0" style={{ background: 'linear-gradient(135deg, #e85002, #ff8a50)' }}>
                {user.email.substring(0, 1).toUpperCase()}
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs text-[var(--text-main)] font-semibold truncate">{user.email}</span>
                <span className="text-[10px] text-[var(--text-dark)] uppercase tracking-wider font-semibold">{user.role}</span>
              </div>
            </div>
          )}
          <div className="flex items-center justify-between px-2">
            <span className="text-xs text-[var(--text-muted)] font-medium">Language / Язык</span>
          </div>
          <div className="flex items-center gap-1 bg-[var(--bg-subtle)] border border-[var(--border)] p-1 rounded-md">
            <button
              onClick={() => setLanguage("en")}
              className={`flex-1 text-center py-1.5 text-xs font-semibold rounded transition-colors ${
                language === "en"
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
              }`}
              aria-label="Switch to English"
            >
              EN
            </button>
            <button
              onClick={() => setLanguage("ru")}
              className={`flex-1 text-center py-1.5 text-xs font-semibold rounded transition-colors ${
                language === "ru"
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
              }`}
              aria-label="Переключить на русский"
            >
              RU
            </button>
          </div>

          <div className="flex items-center justify-between px-2 mt-1">
            <span className="text-xs text-[var(--text-muted)] font-medium">Theme / Тема</span>
          </div>
          <div className="flex items-center gap-1 bg-[var(--bg-subtle)] border border-[var(--border)] p-1 rounded-md">
            <button
              onClick={() => setTheme("light")}
              className={`flex-1 text-center py-1.5 text-xs font-semibold rounded transition-colors ${
                theme === "light"
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
              }`}
              aria-label="Switch to Light Theme"
            >
              {language === "en" ? "Light" : "Светлая"}
            </button>
            <button
              onClick={() => setTheme("dark")}
              className={`flex-1 text-center py-1.5 text-xs font-semibold rounded transition-colors ${
                theme === "dark"
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-panel-hover)]"
              }`}
              aria-label="Switch to Dark Theme"
            >
              {language === "en" ? "Dark" : "Тёмная"}
            </button>
          </div>
          <button
            onClick={logout}
            className="w-full text-left py-2 px-3 hover:bg-[var(--bg-panel-hover)] text-xs text-[var(--color-danger)] font-semibold rounded transition-colors flex items-center gap-2 border border-transparent hover:border-[var(--border)]"
          >
            {t.common.logout}
          </button>
        </div>
      </aside>

      {isSidebarOpen && (
        <div
          onClick={() => setIsSidebarOpen(false)}
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          aria-hidden="true"
        />
      )}

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <header className="p-6 md:p-8 pb-3 md:pb-4 flex flex-col gap-1 shrink-0">
          <div className="text-xs text-[var(--text-dark)] uppercase tracking-wider font-semibold">
            {t.layout.console_title}
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-main)]">
            {getTabTitle()}
          </h1>
        </header>
        <div className="flex-1 p-6 md:p-8 pt-3 md:pt-4 overflow-x-hidden overflow-y-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
