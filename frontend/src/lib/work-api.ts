import { api, ApiError } from "./api";
import type {
  CreateWorkActivityBody,
  PatchWorkActivityBody,
  WorkActivitiesResponse,
  WorkActivity,
  WorkActivityEventsResponse,
} from "@/types/work";

const BASE =
  process.env.NODE_ENV === "development"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";

async function workRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  // Reuse the same auth headers path as api via a thin wrapper calling the shared request pattern.
  // We call through relative paths that the main api client would use; for mutations we need full control.
  // Prefer delegating to fetch with same credentials by importing getAccessToken.
  const { getAccessToken, getApiKey, clearAuth } = await import("./auth");
  const token = getAccessToken();
  const key = getApiKey();
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (key) headers.set("X-API-Key", key);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Falha de rede ao falar com o servidor");
  }

  if (res.status === 403) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/unauthorized")) {
      window.location.href = "/unauthorized";
    }
    throw new ApiError(403, "Acesso não autorizado");
  }
  if (res.status === 401) {
    clearAuth();
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Sessão expirada ou não autorizada");
  }
  if (!res.ok) {
    let detail: string = `Erro ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
      if (Array.isArray(detail))
        detail = detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join(", ");
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export const workApi = {
  list: (params?: {
    status?: string;
    assignee?: string;
    overdue_only?: boolean;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.assignee) q.set("assignee", params.assignee);
    if (params?.overdue_only) q.set("overdue_only", "true");
    if (params?.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return workRequest<WorkActivitiesResponse>(`/api/v1/work/activities${qs ? `?${qs}` : ""}`);
  },

  mine: (limit = 100) =>
    workRequest<WorkActivitiesResponse>(`/api/v1/work/activities/mine?limit=${limit}`),

  get: (id: string) =>
    workRequest<WorkActivity>(`/api/v1/work/activities/${encodeURIComponent(id)}`),

  create: (body: CreateWorkActivityBody) =>
    workRequest<WorkActivity>("/api/v1/work/activities", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  patch: (id: string, body: PatchWorkActivityBody) =>
    workRequest<WorkActivity>(`/api/v1/work/activities/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  events: (id: string) =>
    workRequest<WorkActivityEventsResponse>(
      `/api/v1/work/activities/${encodeURIComponent(id)}/events`
    ),
};

// Silence unused if tree-shaken differently
void api;
