import { api, ApiError } from "./api";
import type {
  CampaignActivityGenerationBody,
  CampaignActivityGenerationResponse,
  CreateWorkActivityBody,
  PatchWorkActivityBody,
  RecordResultBody,
  RecordResultResponse,
  StudentWorkTimelineResponse,
  WorkActivitySummary,
  WorkActivitiesResponse,
  WorkActivity,
  WorkActivityEventsResponse,
  WorkInboxResponse,
  WorkInboxCounts,
  WorkPerspective,
  ClaimWorkBody,
  ResolveWorkBody,
  WorkActionResponse,
} from "@/types/work";

const BASE =
  process.env.NODE_ENV === "development"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";

async function workRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
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
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
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

export type NoContactPriority = {
  as_of: string; window_days: 7; critical_total: number;
  contacted_7d: number; pending_verification: number; without_contact_7d: number;
  candidates: Array<{ id: string; nome: string; matricula: string; risk_score: number }>;
  count_scope: string; policy: string;
};

export const workApi = {
  inbox: (view: WorkPerspective, offset = 0, limit = 25): Promise<WorkInboxResponse> =>
    workRequest<WorkInboxResponse>(`/api/v1/work/inbox?view=${encodeURIComponent(view)}&offset=${offset}&limit=${limit}`),
  inboxCounts: (): Promise<WorkInboxCounts> => workRequest("/api/v1/work/inbox/counts"),
  claim: (id: string, body: ClaimWorkBody): Promise<WorkActionResponse> =>
    workRequest(`/api/v1/work/activities/${encodeURIComponent(id)}/claim`,
      { method: "POST", body: JSON.stringify(body) }),
  resolve: (id: string, body: ResolveWorkBody): Promise<WorkActionResponse> =>
    workRequest(`/api/v1/work/activities/${encodeURIComponent(id)}/resolve`,
      { method: "POST", body: JSON.stringify(body) }),
  list: (params?: {
    status?: string;
    assignee?: string;
    origin_type?: string;
    priority?: string;
    student_id?: string;
    intervention_log_id?: string;
    overdue_only?: boolean;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.assignee) q.set("assignee", params.assignee);
    if (params?.origin_type) q.set("origin_type", params.origin_type);
    if (params?.priority) q.set("priority", params.priority);
    if (params?.student_id) q.set("student_id", params.student_id);
    if (params?.intervention_log_id) q.set("intervention_log_id", params.intervention_log_id);
    if (params?.overdue_only) q.set("overdue_only", "true");
    if (params?.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return workRequest<WorkActivitiesResponse>(`/api/v1/work/activities${qs ? `?${qs}` : ""}`);
  },

  mine: (limit = 100) =>
    workRequest<WorkActivitiesResponse>(`/api/v1/work/activities/mine?limit=${limit}`),

  summary: () => workRequest<WorkActivitySummary>("/api/v1/work/activities/summary"),
  priorityWithoutContact: () => workRequest<NoContactPriority>("/api/v1/work/activities/priority-no-contact"),

  get: (id: string) =>
    workRequest<WorkActivity>(`/api/v1/work/activities/${encodeURIComponent(id)}`),

  create: (body: CreateWorkActivityBody) =>
    workRequest<WorkActivity>("/api/v1/work/activities", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  generateFromCampaign: (body: CampaignActivityGenerationBody) =>
    workRequest<CampaignActivityGenerationResponse>("/api/v1/work/activities/campaign-generated", {
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

  recordResult: (id: string, body: RecordResultBody) =>
    workRequest<RecordResultResponse>(
      `/api/v1/work/activities/${encodeURIComponent(id)}/result`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  /** Linha do tempo integrada do aluno (somente registros persistidos). */
  getTimeline: (studentId: string, limit = 100) =>
    workRequest<StudentWorkTimelineResponse>(
      `/api/v1/students/${encodeURIComponent(studentId)}/work-timeline?limit=${limit}`
    ),
};

void api;
