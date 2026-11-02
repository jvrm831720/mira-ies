import { clearAuth, getAccessToken, getApiKey } from "./auth";
import type {
  AcceptInviteRequest,
  AgentsStatus,
  AuthActionResponse,
  AuthResponse,
  BillingSummary,
  BehaviorProperties,
  BehaviorPropertiesResponse,
  CommunicationPreferenceResponse,
  CommunicationPreferenceUpdate,
  ConsentAuditResponse,
  OptimizedEnqueueResponse,
  SendTimeRecommendation,
  CriticalResponse,
  InviteMemberRequest,
  InviteMemberResponse,
  InvitesResponse,
  LogsResponse,
  MembersResponse,
  ModelInfo,
  PreviewMessage,
  PurchaseCreditsRequest,
  PurchaseCreditsResponse,
  RetentionRunRequest,
  RetentionRunResult,
  RetentionAnalytics,
  RetentionWorkSummary,
  RiskSummary,
  StudentsResponse,
  StudentRisk,
  UploadResponse,
  UploadPreviewResponse,
  UploadStructureResponse,
  MultiUploadPreviewResponse,
  UploadHistoryResponse,
  RiskHistoryResponse,
  StudentRiskHistoryResponse,
  StudentGroupsCatalogResponse,
  StudentGroupsSummaryResponse,
  StudentGroupDetailResponse,
  StudentGroupMembersResponse,
} from "@/types/api";

const BASE =
  process.env.NODE_ENV === "development"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isAuthRoute =
    path.startsWith("/api/v1/auth/") || path.startsWith("/api/v1/org/invites/accept");
  const token = getAccessToken();
  const key = getApiKey();
  const headers = new Headers(init.headers || {});
  if (!isAuthRoute && token) headers.set("Authorization", `Bearer ${token}`);
  else if (!isAuthRoute && key) headers.set("X-API-Key", key);
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
    if (!isAuthRoute) {
      clearAuth();
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/login") &&
        !window.location.pathname.startsWith("/reset-password") &&
        !window.location.pathname.startsWith("/convite")
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
  try {
    return JSON.parse(text) as T;
  } catch {
    return undefined as T;
  }
}

export type OrgMeResponse = {
  role?: string;
  tenant_name?: string;
  tenant_id?: string;
  tenant_slug?: string;
  user_id?: string | null;
  display_name?: string;
  email?: string;
  onboarding_completed?: boolean;
  onboarding_completed_at?: string | null;
};

export const api = {
  baseUrl: BASE,

  loginPassword: (body: { email: string; password: string }) =>
    request<AuthResponse | import("@/types/api").MfaLoginChallenge>("/api/v1/auth/login/password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  verifyMfaLogin: (challenge_token: string, code: string) =>
    request<AuthResponse>("/api/v1/auth/mfa/login/verify", {
      method: "POST",
      body: JSON.stringify({ challenge_token, code }),
    }),

  mfaStatus: () => request<import("@/types/api").MfaStatus>("/api/v1/auth/mfa/status"),
  enrollMfa: () => request<import("@/types/api").MfaEnrollment>("/api/v1/auth/mfa/enroll", { method: "POST" }),
  confirmMfa: (code: string) => request<AuthResponse & { enabled: boolean; recovery_codes: string[] }>("/api/v1/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  regenerateMfaRecoveryCodes: (code: string) => request<import("@/types/api").MfaRecoveryCodes>("/api/v1/auth/mfa/recovery-codes/regenerate", { method: "POST", body: JSON.stringify({ code }) }),
  disableMfa: (code: string) => request<AuthResponse & { enabled: boolean }>("/api/v1/auth/mfa/disable", { method: "POST", body: JSON.stringify({ code }) }),

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

  retentionWorkSummary: () => request<RetentionWorkSummary>("/api/v1/agents/retention/work-summary"),

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

  studentRisk: (id: string) => request<StudentRisk>("/api/v1/students/" + id + "/risk"),

  riskHistory: (params: {
    from: string;
    to: string;
    course?: string;
    risk_level?: string;
    page?: number;
    page_size?: number;
  }) => {
    const q = new URLSearchParams({
      from: params.from,
      to: params.to,
      page: String(params.page ?? 1),
      page_size: String(params.page_size ?? 50),
    });
    if (params.course) q.set("course", params.course);
    if (params.risk_level) q.set("risk_level", params.risk_level);
    return request<RiskHistoryResponse>("/api/v1/risk/history?" + q.toString());
  },

  studentRiskHistory: (
    id: string,
    params?: { from?: string; to?: string; page?: number; page_size?: number }
  ) => {
    const q = new URLSearchParams();
    if (params?.from) q.set("from", params.from);
    if (params?.to) q.set("to", params.to);
    if (params?.page) q.set("page", String(params.page));
    if (params?.page_size) q.set("page_size", String(params.page_size));
    const suffix = q.toString() ? "?" + q.toString() : "";
    return request<StudentRiskHistoryResponse>("/api/v1/students/" + id + "/risk/history" + suffix);
  },

  updateCommunicationPreference: (id: string, optOut: boolean) =>
    request<CommunicationPreferenceResponse>(`/api/v1/students/${id}/communication-preferences`, {
      method: "PATCH",
      body: JSON.stringify({ opt_out: optOut }),
    }),

  updateCommunicationPreferences: (id: string, body: CommunicationPreferenceUpdate) =>
    request<CommunicationPreferenceResponse>(`/api/v1/students/${id}/communication-preferences`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  studentBehaviorProperties: (id: string) =>
    request<BehaviorPropertiesResponse>(`/api/v1/students/${id}/behavior-properties`),

  updateStudentBehaviorProperties: (id: string, properties: BehaviorProperties) =>
    request<{ student_id: string; properties: BehaviorProperties; message_fields: string[] }>(
      `/api/v1/students/${id}/behavior-properties`,
      { method: "PATCH", body: JSON.stringify({ properties }) }
    ),

  retentionSendTime: (id: string, channels?: Array<"whatsapp" | "email" | "sms">) => {
    const q = new URLSearchParams();
    channels?.forEach((channel) => q.append("channels", channel));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return request<SendTimeRecommendation>(`/api/v1/agents/retention/send-time/${id}${suffix}`);
  },

  enqueueRetention: (body: RetentionRunRequest, idempotencyKey?: string) =>
    request<OptimizedEnqueueResponse | { job_id: string; status: string; created_at: number }>(
      "/api/v1/agents/retention/enqueue",
      {
        method: "POST",
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        body: JSON.stringify(body),
      }
    ),

  consentAudit: (id: string, limit = 10) =>
    request<ConsentAuditResponse>(`/api/v1/students/${id}/consent-audit?limit=${limit}`),

  confirmMultipleUploads: async (files: File[], roles: string[], idempotencyKey: string) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    roles.forEach((role) => form.append("file_roles", role));
    return request<{
      message: string;
      students_imported: number;
      persisted: boolean;
      idempotent_replay?: boolean;
      batch?: { id?: string };
      quality?: { rows_created?: number; rows_updated?: number; existing_matches?: number };
    }>("/api/v1/upload/confirm-multiple", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: form,
    });
  },

  previewMultipleUploads: async (files: File[], roles: string[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    roles.forEach((role) => form.append("file_roles", role));
    return request<MultiUploadPreviewResponse>("/api/v1/upload/preview-multiple", {
      method: "POST",
      body: form,
    });
  },

  inspectUploadStructure: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadStructureResponse>("/api/v1/upload/structure", { method: "POST", body: form });
  },

  previewUpload: async (file: File, columnMapping?: Record<string, string>, sheetName?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (columnMapping) form.append("column_mapping", JSON.stringify(columnMapping));
    if (sheetName) form.append("sheet_name", sheetName);
    return request<UploadPreviewResponse>("/api/v1/upload/preview", {
      method: "POST",
      body: form,
    });
  },

  upload: async (
    file: File,
    autoScore = true,
    columnMapping?: Record<string, string>,
    sheetName?: string
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (columnMapping) form.append("column_mapping", JSON.stringify(columnMapping));
    if (sheetName) form.append("sheet_name", sheetName);
    return request<UploadResponse>(`/api/v1/upload?auto_score=${autoScore}`, {
      method: "POST",
      body: form,
    });
  },

  uploadHistory: (limit = 20, offset = 0) =>
    request<UploadHistoryResponse>(`/api/v1/upload/history?limit=${limit}&offset=${offset}`),

  modelInfo: () => request<ModelInfo>("/api/v1/model/info"),

  agentsStatus: () => request<AgentsStatus>("/api/v1/agents/status"),

  retentionAnalytics: (days = 30) =>
    request<RetentionAnalytics>(`/api/v1/agents/retention/analytics?days=${days}`),

  retentionRun: (body: RetentionRunRequest, idempotencyKey?: string) =>
    request<RetentionRunResult>("/api/v1/agents/retention/run", {
      method: "POST",
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      body: JSON.stringify(body),
    }),

  retentionLogs: (params?: {
    limit?: number;
    channel?: string;
    status?: string;
    student_id?: string;
  }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.channel) q.set("channel", params.channel);
    if (params?.status) q.set("status", params.status);
    if (params?.student_id) q.set("student_id", params.student_id);
    const qs = q.toString();
    return request<LogsResponse>(`/api/v1/agents/retention/logs${qs ? `?${qs}` : ""}`);
  },

  retentionPreview: (studentId: string) =>
    request<PreviewMessage>(`/api/v1/agents/retention/preview/${studentId}`),

  listMembers: () => request<MembersResponse>("/api/v1/org/members"),

  listInvites: () => request<InvitesResponse>("/api/v1/org/invites"),

  inviteMember: (body: InviteMemberRequest) =>
    request<InviteMemberResponse>("/api/v1/org/invites", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  acceptInvite: (body: AcceptInviteRequest) =>
    request<AuthResponse>("/api/v1/org/invites/accept", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  me: () => request<OrgMeResponse>("/api/v1/org/me"),

  completeOnboarding: () =>
    request<{ onboarding_completed: boolean; onboarding_completed_at?: string | null }>(
      "/api/v1/org/me/onboarding/complete",
      { method: "POST" }
    ),

  listConnectors: () =>
    request<{
      count: number;
      connectors: Array<{ id: string; name: string; category?: string; description?: string }>;
    }>("/api/v1/connectors"),

  ingestConnector: (connectorId: string, payload: unknown, autoScore = true) =>
    request<Record<string, unknown>>(
      `/api/v1/connectors/${encodeURIComponent(connectorId)}/students?auto_score=${autoScore}`,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  studentGroupsCatalog: () =>
    request<StudentGroupsCatalogResponse>("/api/v1/student-groups/catalog"),

  studentGroupsSummary: () =>
    request<StudentGroupsSummaryResponse>("/api/v1/student-groups/summary"),

  studentGroupDetail: (groupId: string) =>
    request<StudentGroupDetailResponse>(
      "/api/v1/student-groups/" + encodeURIComponent(groupId)
    ),

  studentGroupMembers: (
    groupId: string,
    params?: { limit?: number; cursor?: string | null }
  ) => {
    const query = new URLSearchParams();
    if (params?.limit != null) query.set("limit", String(params.limit));
    if (params?.cursor) query.set("cursor", params.cursor);
    const suffix = query.toString() ? "?" + query.toString() : "";
    return request<StudentGroupMembersResponse>(
      "/api/v1/student-groups/" + encodeURIComponent(groupId) + "/members" + suffix
    );
  },

  billingSummary: () => request<BillingSummary>("/api/v1/billing/summary"),

  purchaseCredits: (body: PurchaseCreditsRequest) =>
    request<PurchaseCreditsResponse>("/api/v1/billing/credits", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
