import { clearAuth, getAccessToken, getApiKey } from "./auth";
import type {
  AgentsStatus,
  AuthActionResponse,
  AuthResponse,
  CommunicationPreferenceResponse,
  CriticalResponse,
  LogsResponse,
  ModelInfo,
  PreviewMessage,
  RetentionRunRequest,
  RetentionRunResult,
  RiskSummary,
  StudentsResponse,
  StudentRisk,
  UploadResponse,
} from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isAuthRoute = path.startsWith("/api/v1/auth/");
  const token = getAccessToken();
  const key = getApiKey();
  const headers = new Headers(init.headers || {});
  if (!isAuthRoute && token) headers.set("Authorization", `Bearer ${token}`);
  else if (!isAuthRoute && key) headers.set("X-API-Key", key);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    if (!isAuthRoute) {
      clearAuth();
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/login") &&
        !window.location.pathname.startsWith("/reset-password")
      ) {
        window.location.href = "/login";
      }
    }
    throw new ApiError(401, "Sessão expirada ou não autorizada");
  }

  if (!res.ok) {
    let detail: string = `Erro ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
      if (Array.isArray(detail)) detail = detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join(", ");
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return undefined as T;
  }
}

export const api = {
  baseUrl: BASE,

  loginPassword: (body: { email: string; password: string }) =>
    request<AuthResponse>("/api/v1/auth/login/password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  requestWhatsappCode: (phone: string) =>
    request<AuthActionResponse>("/api/v1/auth/whatsapp/request", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  verifyWhatsappCode: (phone: string, code: string) =>
    request<AuthResponse>("/api/v1/auth/whatsapp/verify", {
      method: "POST",
      body: JSON.stringify({ phone, code }),
    }),

  forgotPassword: (email: string) =>
    request<AuthActionResponse>("/api/v1/auth/password/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, newPassword: string) =>
    request<AuthActionResponse>("/api/v1/auth/password/reset", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  async validateKey(key: string) {
    const res = await fetch(`${BASE}/api/v1/agents/status`, {
      headers: { "X-API-Key": key },
    });
    if (!res.ok) throw new ApiError(res.status, "Não foi possível validar a chave");
    return res.json() as Promise<AgentsStatus>;
  },

  riskSummary: (batchId?: string) =>
    request<RiskSummary>(
      `/api/v1/risk/summary${batchId ? `?batch_id=${encodeURIComponent(batchId)}` : ""}`
    ),

  riskCritical: (limit = 50, batchId?: string) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (batchId) q.set("batch_id", batchId);
    return request<CriticalResponse>(`/api/v1/risk/critical?${q}`);
  },

  students: (params?: { batch_id?: string; risk_level?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.batch_id) q.set("batch_id", params.batch_id);
    if (params?.risk_level) q.set("risk_level", params.risk_level);
    if (params?.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return request<StudentsResponse>(`/api/v1/students${qs ? `?${qs}` : ""}`);
  },

  studentRisk: (id: string) => request<StudentRisk>(`/api/v1/students/${id}/risk`),

  updateCommunicationPreference: (id: string, optOut: boolean) =>
    request<CommunicationPreferenceResponse>(`/api/v1/students/${id}/communication-preferences`, {
      method: "PATCH",
      body: JSON.stringify({ opt_out: optOut }),
    }),

  upload: async (file: File, autoScore = true) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>(`/api/v1/upload?auto_score=${autoScore}`, {
      method: "POST",
      body: form,
    });
  },

  modelInfo: () => request<ModelInfo>("/api/v1/model/info"),

  agentsStatus: () => request<AgentsStatus>("/api/v1/agents/status"),

  retentionRun: (body: RetentionRunRequest) =>
    request<RetentionRunResult>("/api/v1/agents/retention/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  retentionLogs: (params?: { limit?: number; channel?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.channel) q.set("channel", params.channel);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return request<LogsResponse>(`/api/v1/agents/retention/logs${qs ? `?${qs}` : ""}`);
  },

  retentionPreview: (studentId: string) =>
    request<PreviewMessage>(`/api/v1/agents/retention/preview/${studentId}`),
};
