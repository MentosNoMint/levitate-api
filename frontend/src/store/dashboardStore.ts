import { create } from "zustand";

export interface VirtualKey {
  id: string;
  name: string;
  key: string;
  status: "active" | "paused" | "warning";
  monthlyUsage: number;
  monthlyLimit: number;
  rpmLimit: number;
  priority: "High" | "Medium" | "Low";
  createdAt: string;
}

export interface Credential {
  id: string;
  name: string;
  provider: string;
  type: "managed" | "byo";
  priority: number;
  weight: number;
  status: "active" | "cooldown" | "exhausted" | "error" | "degraded";
  concurrency: number;
  requestsCount: number;
  latencyAvg: number;
  errorRate: number;
  details: string;
  quotaTotalTokens: number | null;
  quotaUsedTokens: number;
  quotaWindow: number | null;
  resetAt: string | null;
  models: string[];
  modelQuotas?: Record<string, number>;
  tier?: string | null;
  loadError?: string | null;
  quotaError?: string | null;
}

export interface UsageLog {
  id: string;
  timestamp: string;
  virtualKey: string;
  destinationPool: string;
  model: string;
  latency: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  cost: number;
  status: number;
  statusText: string;
}

export interface SystemStats {
  activeRoutingPools: string;
  gatewaySuccessRate: number;
  totalRoutedTokens: number;
  totalRequests: number;
  tokenUsageHistory: { timestamp: string; value: number }[];
}

interface BackendVirtualKey {
  id: string;
  user_id: string;
  name: string;
  monthly_token_limit: number | null;
  rpm_limit: number | null;
  allowed_model_groups: string[] | null;
  status: "active" | "paused" | "warning";
  monthly_usage?: number;
}

interface BackendCredential {
  id: string;
  type: string;
  name: string;
  provider: string;
  base_url: string | null;
  models: string[] | null;
  quota_total_tokens: number | null;
  quota_used_tokens: number;
  quota_window: number | null;
  reset_at: string | null;
  rpm_limit: number | null;
  concurrency_limit: number | null;
  priority: number;
  weight: number;
  status: "active" | "cooldown" | "exhausted" | "error" | "degraded";
  expires_at: string | null;
  last_check_at: string | null;
  model_quotas: Record<string, number> | null;
  tier: string | null;
  load_error: string | null;
  quota_error: string | null;
}

interface BackendUsageLog {
  id: string;
  virtual_key_id: string | null;
  credential_id: string | null;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  est_cost: number;
  latency_ms: number;
  status: string;
  created_at: string | null;
}

interface BackendAuditLog {
  id: string;
  event_type: string;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
}

interface BackendLogsResponse {
  usage_events: BackendUsageLog[];
  audit_logs: BackendAuditLog[];
}

interface BackendStatsResponse {
  total_requests: number;
  success_rate: number;
  token_consumption: {
    prompt: number;
    completion: number;
    total: number;
  };
  token_usage_history: { timestamp: string; value: number }[];
}

interface UserProfile {
  email: string;
  role: string;
  id: string;
}

interface DashboardState {
  language: "en" | "ru";
  theme: "dark" | "light";
  isLoading: boolean;
  isAuthLoading: boolean;
  user: UserProfile | null;
  token: string | null;
  googleOauthConfigured: boolean;
  virtualKeys: VirtualKey[];
  credentials: Credential[];
  logs: UsageLog[];
  stats: SystemStats;
  lastGeneratedKey: string | null;
  setLanguage: (lang: "en" | "ru") => void;
  setTheme: (theme: "dark" | "light") => void;
  setIsLoading: (loading: boolean) => void;
  setToken: (token: string | null) => void;
  clearGeneratedKey: () => void;
  fetchConfig: () => Promise<void>;
  fetchUser: () => Promise<void>;
  logout: () => void;
  fetchData: () => Promise<void>;
  addVirtualKey: (name: string, monthlyLimit: number, rpmLimit: number, priority: "High" | "Medium" | "Low") => Promise<void>;
  toggleVirtualKeyStatus: (id: string) => Promise<void>;
  updateVirtualKeyBudget: (id: string, monthlyLimit: number, rpmLimit: number) => Promise<void>;
  addCredential: (credential: {
    name: string;
    provider: string;
    type: "managed" | "byo";
    priority: number;
    weight: number;
    concurrency: number;
    apiKey: string;
    baseUrl?: string;
    quotaTotalTokens?: number | null;
    quotaWindow?: number | null;
    models?: string[];
  }) => Promise<void>;
  updateCredentialPriorityWeight: (
    id: string,
    priority: number,
    weight: number,
    concurrency: number,
    quotaTotalTokens?: number | null,
    quotaWindow?: number | null,
    models?: string[]
  ) => Promise<void>;
  toggleCredentialStatus: (id: string, status: Credential["status"]) => Promise<void>;
  simulateLog: () => Promise<void>;
  clearLogs: () => Promise<void>;
  refreshCredentialQuota: (id: string) => Promise<void>;
  refreshAllQuotas: () => Promise<void>;
  deleteCredential: (id: string) => Promise<void>;
}

const getApiUrl = (): string => {
  if (typeof window !== "undefined") {
    return window.location.protocol + "//" + window.location.hostname + ":8000";
  }
  return "http://localhost:8000";
};

const apiFetch = async (path: string, options: RequestInit = {}, token: string | null = null): Promise<Response> => {
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${getApiUrl()}${path}`, {
    ...options,
    headers,
  });
};

export const useDashboardStore = create<DashboardState>((set, get) => ({
  language: "en",
  theme: "dark",
  isLoading: false,
  isAuthLoading: true,
  user: null,
  token: null,
  googleOauthConfigured: false,
  virtualKeys: [],
  credentials: [],
  logs: [],
  lastGeneratedKey: null,
  stats: {
    activeRoutingPools: "0 / 0",
    gatewaySuccessRate: 100,
    totalRoutedTokens: 0,
    totalRequests: 0,
    tokenUsageHistory: [],
  },

  setLanguage: (lang) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("language", lang);
    }
    set({ language: lang });
  },
  setTheme: (theme) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("theme", theme);
      document.documentElement.setAttribute("data-theme", theme);
    }
    set({ theme });
  },

  setIsLoading: (loading) => set({ isLoading: loading }),
  setToken: (token) => {
    if (typeof window !== "undefined") {
      if (token) {
        localStorage.setItem("auth_token", token);
        document.cookie = `auth_token=${token}; path=/; max-age=2592000; SameSite=Lax`;
      } else {
        localStorage.removeItem("auth_token");
        document.cookie = "auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      }
    }
    set({ token });
  },
  clearGeneratedKey: () => set({ lastGeneratedKey: null }),

  fetchConfig: async () => {
    try {
      const resp = await apiFetch("/admin/auth/config");
      if (resp.ok) {
        const data = await resp.json() as { google_oauth_configured: boolean };
        set({ googleOauthConfigured: data.google_oauth_configured });
      }
    } catch {
      // Ignored config error fallback
    }
  },

  fetchUser: async () => {
    const { token } = get();
    if (!token) {
      set({ user: null, isAuthLoading: false });
      return;
    }
    try {
      const resp = await apiFetch("/admin/auth/me", {}, token);
      if (resp.ok) {
        const user = await resp.json() as UserProfile;
        set({ user, isAuthLoading: false });
      } else {
        set({ user: null, token: null, isAuthLoading: false });
        if (typeof window !== "undefined") {
          localStorage.removeItem("auth_token");
          document.cookie = "auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
        }
      }
    } catch {
      set({ user: null, isAuthLoading: false });
    }
  },

  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
      document.cookie = "auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    }
    set({ user: null, token: null, virtualKeys: [], credentials: [], logs: [] });
  },

  fetchData: async () => {
    const { token } = get();
    if (!token) return;
    set({ isLoading: true });
    try {
      const [keysResp, credsResp, statsResp, logsResp] = await Promise.all([
        apiFetch("/admin/virtual-keys", {}, token),
        apiFetch("/admin/credentials", {}, token),
        apiFetch("/admin/stats", {}, token),
        apiFetch("/admin/logs", {}, token),
      ]);

      let virtualKeys: VirtualKey[] = [];
      if (keysResp.ok) {
        const keysData = await keysResp.json() as BackendVirtualKey[];
        virtualKeys = keysData.map((k) => ({
          id: k.id,
          name: k.name,
          key: "sk-gateway-••••••••••••",
          status: k.status,
          monthlyUsage: k.monthly_usage || 0,
          monthlyLimit: k.monthly_token_limit || 0,
          rpmLimit: k.rpm_limit || 0,
          priority: k.monthly_token_limit && k.monthly_token_limit > 5000000 ? "High" : "Medium",
          createdAt: "",
        }));
      }

      let credentials: Credential[] = [];
      if (credsResp.ok) {
        const credsData = await credsResp.json() as BackendCredential[];
        credentials = credsData.map((c) => ({
          id: c.id,
          name: c.name,
          provider: c.provider,
          type: c.type === "antigravity" ? "managed" : "byo",
          priority: c.priority,
          weight: c.weight,
          status: c.status,
          concurrency: c.concurrency_limit || 0,
          requestsCount: 0,
          latencyAvg: 0,
          errorRate: 0,
          details: JSON.stringify({ provider: c.provider, baseUrl: c.base_url, models: c.models }, null, 2),
          quotaTotalTokens: c.quota_total_tokens,
          quotaUsedTokens: c.quota_used_tokens,
          quotaWindow: c.quota_window,
          resetAt: c.reset_at,
          models: c.models || [],
          modelQuotas: c.model_quotas || undefined,
          tier: c.tier,
          loadError: c.load_error,
          quotaError: c.quota_error,
        }));
      }

      let logs: UsageLog[] = [];
      if (logsResp.ok) {
        const logsData = await logsResp.json() as BackendLogsResponse;
        logs = logsData.usage_events.map((u) => {
          const vkey = virtualKeys.find((k) => k.id === u.virtual_key_id);
          const cred = credentials.find((c) => c.id === u.credential_id);
          return {
            id: u.id,
            timestamp: u.created_at ? u.created_at.replace("T", " ").substring(0, 19) : "",
            virtualKey: vkey ? vkey.name : "unknown",
            destinationPool: cred ? cred.name : "unknown",
            model: u.model,
            latency: u.latency_ms,
            promptTokens: u.prompt_tokens,
            completionTokens: u.completion_tokens,
            totalTokens: u.prompt_tokens + u.completion_tokens,
            cost: u.est_cost,
            status: u.status === "success" ? 200 : 500,
            statusText: u.status === "success" ? "200 OK" : "500 Error",
          };
        });
      }

      let stats: SystemStats = {
        activeRoutingPools: "0 / 0",
        gatewaySuccessRate: 100,
        totalRoutedTokens: 0,
        totalRequests: 0,
        tokenUsageHistory: [],
      };

      if (statsResp.ok) {
        const statsData = await statsResp.json() as BackendStatsResponse;
        const activePools = credentials.filter((c) => c.status === "active").length;
        stats = {
          activeRoutingPools: `${activePools} / ${credentials.length}`,
          gatewaySuccessRate: statsData.success_rate,
          totalRoutedTokens: Number((statsData.token_consumption.total / 1000000).toFixed(2)),
          totalRequests: statsData.total_requests,
          tokenUsageHistory: statsData.token_usage_history || [],
        };
      }

      set({ virtualKeys, credentials, logs, stats, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  addVirtualKey: async (name, monthlyLimit, rpmLimit, priority) => {
    const { token, fetchData } = get();
    try {
      const resp = await apiFetch("/admin/virtual-keys", {
        method: "POST",
        body: JSON.stringify({
          name,
          monthly_token_limit: monthlyLimit,
          rpm_limit: rpmLimit,
        }),
      }, token);

      if (resp.ok) {
        const res = await resp.json() as { key: string };
        set({ lastGeneratedKey: res.key });
        await fetchData();
      }
    } catch {
      // Handled error state
    }
  },

  toggleVirtualKeyStatus: async (id) => {
    const { token, virtualKeys, fetchData } = get();
    const key = virtualKeys.find((k) => k.id === id);
    if (!key) return;
    const nextStatus = key.status === "active" ? "paused" : "active";
    try {
      await apiFetch(`/admin/virtual-keys/${id}`, {
        method: "PUT",
        body: JSON.stringify({ status: nextStatus }),
      }, token);
      await fetchData();
    } catch {
      // Ignored update error fallback
    }
  },

  updateVirtualKeyBudget: async (id, monthlyLimit, rpmLimit) => {
    const { token, fetchData } = get();
    try {
      await apiFetch(`/admin/virtual-keys/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          monthly_token_limit: monthlyLimit,
          rpm_limit: rpmLimit,
        }),
      }, token);
      await fetchData();
    } catch {
      // Ignored budget edit error fallback
    }
  },

  addCredential: async (cred) => {
    const { token, fetchData } = get();
    const typeMapping = cred.type === "managed" ? "antigravity" : "byo_upstream";
    try {
      await apiFetch("/admin/credentials", {
        method: "POST",
        body: JSON.stringify({
          type: typeMapping,
          name: cred.name,
          provider: cred.provider,
          secret: cred.apiKey,
          base_url: cred.baseUrl,
          concurrency_limit: cred.concurrency,
          priority: cred.priority,
          weight: cred.weight,
          quota_total_tokens: cred.quotaTotalTokens,
          quota_window: cred.quotaWindow,
          models: cred.models,
        }),
      }, token);
      await fetchData();
    } catch {
    }
  },

  updateCredentialPriorityWeight: async (id, priority, weight, concurrency, quotaTotalTokens, quotaWindow, models) => {
    const { token, fetchData } = get();
    try {
      await apiFetch(`/admin/credentials/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          priority,
          weight,
          concurrency_limit: concurrency,
          quota_total_tokens: quotaTotalTokens,
          quota_window: quotaWindow,
          models: models,
        }),
      }, token);
      await fetchData();
    } catch {
    }
  },

  toggleCredentialStatus: async (id, status) => {
    const { token, fetchData } = get();
    try {
      await apiFetch(`/admin/credentials/${id}`, {
        method: "PUT",
        body: JSON.stringify({ status }),
      }, token);
      await fetchData();
    } catch {
      // Ignored status edit error fallback
    }
  },

  simulateLog: async () => {
    const { token, fetchData } = get();
    try {
      await apiFetch("/admin/logs/simulate", { method: "POST" }, token);
      await fetchData();
    } catch {
      // Simulation error fallback
    }
  },

  clearLogs: async () => {
    const { token, fetchData } = get();
    try {
      await apiFetch("/admin/logs", { method: "DELETE" }, token);
      await fetchData();
    } catch {
      // Ignored logs clear error fallback
    }
  },

  deleteCredential: async (id) => {
    const { token, fetchData } = get();
    try {
      await apiFetch(`/admin/credentials/${id}`, { method: "DELETE" }, token);
      await fetchData();
    } catch {
      // Ignored delete error fallback
    }
  },

  refreshCredentialQuota: async (id) => {
    const { token, fetchData } = get();
    try {
      await apiFetch(`/admin/credentials/${id}/refresh-quota`, { method: "POST" }, token);
      await fetchData();
    } catch {
      // Ignored refresh quota error fallback
    }
  },

  refreshAllQuotas: async () => {
    const { token, fetchData } = get();
    try {
      await apiFetch("/admin/credentials/refresh-all-quotas", { method: "POST" }, token);
      await fetchData();
    } catch {
      // Ignored refresh all quotas error fallback
    }
  },
}));
