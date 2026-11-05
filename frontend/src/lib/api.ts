import { clearAuth, getAccessToken, getApiKey, setAccessToken } from "./auth";
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
    path === "/api/v1/auth/login/password" ||
    path.startsWith("/api/v1/auth/whatsapp/") ||
    path.startsWith("/api/v1/auth/email/") ||
    path.startsWith("/api/v1/auth/password/") ||
    path.startsWith("/api/v1/auth/mfa/login/") ||
    path === "/api/v1/org/invites/accept";
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

export type RMTotvsJobStatus = "queued" | "running" | "retry_wait" | "cancel_requested" | "publishing" | "cancelled" | "succeeded" | "failed";
export type RMTotvsScope = {
  id: string; coligada_id: string; source_name: string; entity_name: string;
  schema_version: string; current_snapshot_run_id?: string | null;
  created_at: string; updated_at: string;
};
export type RMTotvsJob = {
  id: string; scope_id: string; coligada_id: string; source_name: string;
  entity_name: string; schema_version: string; snapshot_run_id?: string | null;
  status: RMTotvsJobStatus; attempts: number; max_attempts: number;
  available_at?: string | null; created_at: string; started_at?: string | null;
  finished_at?: string | null; error_code?: string | null; error_message?: string | null;
  request?: { mode?: string; page_size?: number };
};
export type RMTotvsJobEvent = {
  event_type: string; severity: "info" | "warning" | "error" | string;
  details?: Record<string, unknown>; created_at: string;
};
export type RMTotvsJobDetail = RMTotvsJob & { events: RMTotvsJobEvent[] };
export type RMTotvsJobsResponse = { total: number; limit: number; offset: number; jobs: RMTotvsJob[] };
export type RMTotvsMetrics = {
  jobs_by_status: Record<string, number>; queue_depth: number;
  active_jobs: number; average_duration_seconds?: number | null;
};

export type JacadSyncJob = {
  job_id: string;
  status: "queued" | "running" | "retrying" | "completed" | "failed" | string;
  progress?: {
    stage?: string; percent?: number; students?: number; enrollments?: number;
    financial_summaries?: number; contracts_total?: number; contracts_done?: number;
    discipline_pairs_total?: number; discipline_pairs_done?: number;
    assessment_groups_total?: number; assessment_groups_done?: number;
  } | null;
  result?: {
    source_records?: number; students_imported?: number; enrollments_received?: number;
    financial_summaries_received?: number; students_with_financial_status?: number;
    contracts_consulted?: number; discipline_pairs_consulted?: number; classes_consulted?: number;
    assessment_groups?: number; scoring?: string;
  } | null;
  last_error?: string | null;
  attempt?: number;
  created_at?: number;
  updated_at?: number;
};

export type SponteSyncJob = {
  job_id: string;
  status: "queued" | "running" | "retrying" | "completed" | "failed" | string;
  progress?: { stage?: string; endpoint?: string | null; endpoint_index?: number; endpoint_count?: number; percent?: number; pages_done?: number; pages_total?: number } | null;
  result?: { endpoints?: Record<string, number>; watermarks?: Record<string, string>; students_updated?: number; scoring?: string } | null;
  last_error?: string | null;
  attempt?: number;
};

export type OrgMeResponse = {
  role?: string;
  permissions?: string[] | null;
  custom_role_id?: string | null;
  tenant_name?: string;
  tenant_id?: string;
  tenant_slug?: string;
  user_id?: string | null;
  display_name?: string;
  email?: string;
  membership_id?: string | null;
  onboarding_completed?: boolean;
  onboarding_completed_at?: string | null;
};

export type WorkspaceItem = {
  membership_id: string | null;
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
  custom_role_id: string | null;
  status: string;
  is_current: boolean;
  source: string;
};

export type WorkspacesResponse = {
  workspaces: WorkspaceItem[];
  current_membership_id: string | null;
  current_tenant_id: string;
};

export type SwitchWorkspaceResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  membership_id: string;
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
};

export const api = {
  baseUrl: BASE,

  loginPassword: (body: { email: string; password: string }) =>
    request<AuthResponse | import("@/types/api").MfaLoginChallenge>("/api/v1/auth/login/password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  beginRequiredMfaEnrollment: (challenge_token: string) =>
    request<import("@/types/api").MfaEnrollment>("/api/v1/auth/mfa/login/enroll", {
      method: "POST",
      body: JSON.stringify({ challenge_token }),
    }),
  confirmRequiredMfaEnrollment: (challenge_token: string, code: string) =>
    request<AuthResponse & { enabled: boolean; recovery_codes: string[] }>("/api/v1/auth/mfa/login/enroll/confirm", {
      method: "POST",
      body: JSON.stringify({ challenge_token, code }),
    }),

  verifyMfaLogin: (challenge_token: string, code: string) =>
    request<AuthResponse>("/api/v1/auth/mfa/login/verify", {
      method: "POST",
      body: JSON.stringify({ challenge_token, code }),
    }),

  mfaStatus: () => request<import("@/types/api").MfaStatus>("/api/v1/auth/mfa/status"),
  mfaPolicy: () => request<import("@/types/api").MfaPolicy>("/api/v1/auth/mfa/policy"),
  updateMfaPolicy: (body: import("@/types/api").MfaPolicy) =>
    request<AuthResponse & import("@/types/api").MfaPolicy>("/api/v1/auth/mfa/policy", { method: "PUT", body: JSON.stringify(body) }),
  stepUpMfa: (code: string) => request<AuthResponse>("/api/v1/auth/mfa/step-up", { method: "POST", body: JSON.stringify({ code }) }),
  mfaSessions: () => request<import("@/types/api").MfaSessionsResponse>("/api/v1/auth/mfa/sessions"),
  revokeMfaSession: (sessionId: string) => request<{ revoked: boolean; session_id: string }>(`/api/v1/auth/mfa/sessions/${sessionId}`, { method: "DELETE" }),
  revokeOtherMfaSessions: () => request<{ revoked_count: number }>("/api/v1/auth/mfa/sessions/revoke-others", { method: "POST" }),
  adminRevokeMemberSessions: (userId: string) => request<{ revoked_count: number; user_id: string }>(`/api/v1/auth/mfa/admin/users/${userId}/revoke-sessions`, { method: "POST" }),
  enrollMfa: () => request<import("@/types/api").MfaEnrollment>("/api/v1/auth/mfa/enroll", { method: "POST" }),
  confirmMfa: (code: string) => request<AuthResponse & { enabled: boolean; recovery_codes: string[] }>("/api/v1/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  regenerateMfaRecoveryCodes: (code: string) => request<import("@/types/api").MfaRecoveryCodes>("/api/v1/auth/mfa/recovery-codes/regenerate", { method: "POST", body: JSON.stringify({ code }) }),
  disableMfa: (code: string) => request<AuthResponse & { enabled: boolean }>("/api/v1/auth/mfa/disable", { method: "POST", body: JSON.stringify({ code }) }),

  requestEmailCode: (email: string) =>
    request<AuthActionResponse>("/api/v1/auth/email/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  verifyEmailCode: (email: string, code: string) =>
    request<AuthResponse | import("@/types/api").MfaLoginChallenge | { onboarding_required: true; email: string }>("/api/v1/auth/email/verify", {
      method: "POST",
      body: JSON.stringify({ email, code }),
    }),

  requestWhatsappCode: (phone: string) =>
    request<AuthActionResponse>("/api/v1/auth/whatsapp/request", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  verifyWhatsappCode: (phone: string, code: string) =>
    request<AuthResponse | import("@/types/api").MfaLoginChallenge>("/api/v1/auth/whatsapp/verify", {
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

  retentionJobStatus: (jobId: string) =>
    request<import("@/types/api").RetentionJob>(
      `/api/v1/agents/retention/jobs/${encodeURIComponent(jobId)}`
    ),

  pauseRetentionJob: (jobId: string) =>
    request<import("@/types/api").RetentionJob>(
      `/api/v1/agents/retention/jobs/${encodeURIComponent(jobId)}/pause`,
      { method: "POST" }
    ),

  resumeRetentionJob: (jobId: string) =>
    request<import("@/types/api").RetentionJob>(
      `/api/v1/agents/retention/jobs/${encodeURIComponent(jobId)}/resume`,
      { method: "POST" }
    ),

  cancelRetentionJob: (jobId: string) =>
    request<import("@/types/api").RetentionJob>(
      `/api/v1/agents/retention/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" }
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

  permanenceAnalytics: (params?: {
    days?: number;
    academic_period?: string;
    course?: string;
    campaign_id?: string;
    channel?: "whatsapp" | "email" | "sms";
  }) => {
    const q = new URLSearchParams({ days: String(params?.days ?? 365) });
    if (params?.academic_period) q.set("academic_period", params.academic_period);
    if (params?.course) q.set("course", params.course);
    if (params?.campaign_id) q.set("campaign_id", params.campaign_id);
    if (params?.channel) q.set("channel", params.channel);
    return request<import("@/types/api").PermanenceAnalytics>(`/api/v1/outcomes/analytics?${q.toString()}`);
  },

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


  retentionCampaignProposals: () =>
    request<import("@/types/api").RetentionCampaignProposalsResponse>(
      "/api/v1/agents/retention/campaigns/intelligence/proposals"
    ),

  retentionCampaignOpportunities: () =>
    request<import("@/types/api").RetentionCampaignOpportunitiesResponse>(
      "/api/v1/agents/retention/campaigns/intelligence/opportunities"
    ),

  createRetentionCampaignProposal: (groupIds: string[]) =>
    request<import("@/types/api").RetentionCampaignProposal>(
      "/api/v1/agents/retention/campaigns/intelligence/proposals",
      { method: "POST", body: JSON.stringify({ group_ids: groupIds }) }
    ),

  updateRetentionCampaignProposal: (id: string, body: Partial<Pick<
    import("@/types/api").RetentionCampaignProposal,
    "title" | "objective" | "strategy" | "recommended_channels" | "cadence_days" | "message_brief"
  >>) =>
    request<import("@/types/api").RetentionCampaignProposal>(
      `/api/v1/agents/retention/campaigns/intelligence/proposals/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(body) }
    ),

  reviewRetentionCampaignProposal: (id: string) =>
    request<import("@/types/api").RetentionCampaignProposal>(
      `/api/v1/agents/retention/campaigns/intelligence/proposals/${encodeURIComponent(id)}/review`,
      { method: "POST" }
    ),

  requestRetentionCampaignProposalChanges: (id: string, note: string) =>
    request<import("@/types/api").RetentionCampaignProposal>(
      `/api/v1/agents/retention/campaigns/intelligence/proposals/${encodeURIComponent(id)}/request-changes`,
      { method: "POST", body: JSON.stringify({ note }) }
    ),

  attestRetentionCampaignProposalAuthorization: (id: string, body: {
    basis: string; evidence_reference: string; attestation: boolean;
  }) =>
    request<import("@/types/api").RetentionCampaignProposal>(
      `/api/v1/agents/retention/campaigns/intelligence/proposals/${encodeURIComponent(id)}/authorization-attestation`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  approveRetentionCampaignProposal: (id: string) =>
    request<import("@/types/api").RetentionCampaignProposal>(
      `/api/v1/agents/retention/campaigns/intelligence/proposals/${encodeURIComponent(id)}/approve`,
      { method: "POST" }
    ),

  retentionCampaignProposalAudit: (id: string) =>
    request<import("@/types/api").RetentionCampaignProposalAudit>(
      `/api/v1/agents/retention/campaigns/intelligence/proposals/${encodeURIComponent(id)}/audit`
    ),

  listMembers: () => request<MembersResponse>("/api/v1/org/members"),

  tenantRoleCatalog: () => request<import("@/types/api").TenantRoleCatalogResponse>("/api/v1/org/roles/catalog"),
  tenantRoles: () => request<import("@/types/api").TenantRolesResponse>("/api/v1/org/roles"),
  createTenantRole: (body: import("@/types/api").TenantRolePayload) =>
    request<{ role: import("@/types/api").TenantRole }>("/api/v1/org/roles", { method: "POST", body: JSON.stringify(body) }),
  updateTenantRole: (id: string, body: import("@/types/api").TenantRolePayload) =>
    request<{ role: import("@/types/api").TenantRole }>(`/api/v1/org/roles/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  duplicateTenantRole: (id: string) =>
    request<{ role: import("@/types/api").TenantRole }>(`/api/v1/org/roles/${encodeURIComponent(id)}/duplicate`, { method: "POST" }),
  deactivateTenantRole: (id: string) =>
    request<{ deactivated: boolean }>(`/api/v1/org/roles/${encodeURIComponent(id)}/deactivate`, { method: "POST" }),
  tenantRoleMembers: (id: string) =>
    request<import("@/types/api").TenantRoleMembersResponse>(`/api/v1/org/roles/${encodeURIComponent(id)}/members`),
  assignTenantRole: (userId: string, customRoleId: string | null) =>
    request<{ member_id: string; custom_role_id: string | null; sessions_invalidated: boolean }>(
      `/api/v1/org/members/${encodeURIComponent(userId)}/role`,
      { method: "POST", body: JSON.stringify({ custom_role_id: customRoleId }) }
    ),
  memberEffectivePermissions: (userId: string) =>
    request<{ member_id: string; legacy_role: string; permissions: string[]; custom_role?: import("@/types/api").TenantRole | null }>(
      `/api/v1/org/members/${encodeURIComponent(userId)}/permissions`
    ),
  tenantRoleAudit: () => request<import("@/types/api").TenantRoleAuditResponse>("/api/v1/org/role-audit"),

  listInvites: () => request<InvitesResponse>("/api/v1/org/invites"),

  inviteMember: (body: InviteMemberRequest) =>
    request<InviteMemberResponse>("/api/v1/org/invites", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  acceptInvite: (body: AcceptInviteRequest) =>
    request<AuthResponse | import("@/types/api").MfaLoginChallenge>("/api/v1/org/invites/accept", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  acceptExistingInvite: (body: { token: string }) =>
    request<AuthResponse>("/api/v1/org/invites/accept-existing", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  me: () => request<OrgMeResponse>("/api/v1/org/me"),

  completeOnboarding: () =>
    request<{ onboarding_completed: boolean; onboarding_completed_at?: string | null }>(
      "/api/v1/org/me/onboarding/complete",
      { method: "POST" }
    ),

  listWorkspaces: () => request<WorkspacesResponse>("/api/v1/org/workspaces"),

  switchWorkspace: async (body: { membership_id?: string; tenant_id?: string }) => {
    const response = await request<SwitchWorkspaceResponse>("/api/v1/org/workspaces/switch", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (response.access_token) setAccessToken(response.access_token);
    return response;
  },

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


  jacadConnection: () =>
    request<{
      provider: string; configured: boolean; enabled?: boolean; base_url?: string;
      default_org_id?: number | null; status?: string; last_tested_at?: string | null;
      last_sync_at?: string | null; last_sync_status?: string | null;
      last_sync_records?: number; last_error?: string | null; credential_configured?: boolean;
    }>("/api/v1/integrations/jacad"),

  configureJacad: (body: { base_url: string; api_token?: string; default_org_id?: number | null }) =>
    request<Record<string, unknown>>("/api/v1/integrations/jacad", {
      method: "PUT", body: JSON.stringify(body),
    }),

  testJacad: () =>
    request<{ status: string; authenticated: boolean; students_endpoint: boolean; sample_records: number }>(
      "/api/v1/integrations/jacad/test", { method: "POST" }
    ),

  syncJacad: () =>
    request<{ status: string; job_id: string; deduplicated?: boolean; progress?: Record<string, unknown> }>(
      "/api/v1/integrations/jacad/sync", { method: "POST" }
    ),

  jacadSyncCurrent: () =>
    request<JacadSyncJob | null>("/api/v1/integrations/jacad/sync/current"),

  jacadSyncStatus: (jobId: string) =>
    request<JacadSyncJob>(`/api/v1/integrations/jacad/sync/${encodeURIComponent(jobId)}`),

  retryJacadSync: (jobId: string) =>
    request<{ job_id: string; status: string; progress?: Record<string, unknown> }>(
      `/api/v1/integrations/jacad/sync/${encodeURIComponent(jobId)}/retry`, { method: "POST" }
    ),

  sponteConnection: () =>
    request<{
      provider: string; configured: boolean; enabled?: boolean; client_code?: number;
      initial_extraction_date?: string; status?: string; last_tested_at?: string | null;
      last_sync_at?: string | null; last_sync_status?: string | null; last_sync_records?: number;
      last_error?: string | null; credential_configured?: boolean; sync_watermarks?: Record<string, string>;
    }>("/api/v1/integrations/sponte"),

  configureSponte: (body: { api_key?: string; client_code: number; initial_extraction_date: string }) =>
    request<Record<string, unknown>>("/api/v1/integrations/sponte", {
      method: "PUT", body: JSON.stringify(body),
    }),

  testSponte: () =>
    request<{ status: string; endpoint: string; records_sampled: number; client_code: number }>(
      "/api/v1/integrations/sponte/test", { method: "POST" }
    ),

  syncSponte: () =>
    request<{ job_id: string; status: string; deduplicated?: boolean; progress?: Record<string, unknown> }>(
      "/api/v1/integrations/sponte/sync", { method: "POST" }
    ),

  sponteSyncCurrent: () =>
    request<SponteSyncJob | null>("/api/v1/integrations/sponte/sync/current"),

  sponteSyncStatus: (jobId: string) =>
    request<SponteSyncJob>(`/api/v1/integrations/sponte/sync/${encodeURIComponent(jobId)}`),

  retrySponteSync: (jobId: string) =>
    request<{ job_id: string; status: string; progress?: Record<string, unknown> }>(
      `/api/v1/integrations/sponte/sync/${encodeURIComponent(jobId)}/retry`, { method: "POST" }
    ),

  totvsRmScopes: () => request<{ scopes: RMTotvsScope[] }>("/api/v1/integrations/totvs-rm/scopes"),

  totvsRmJobs: (params?: { status?: string; coligada_id?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.coligada_id) query.set("coligada_id", params.coligada_id);
    if (params?.limit != null) query.set("limit", String(params.limit));
    if (params?.offset != null) query.set("offset", String(params.offset));
    const suffix = query.toString() ? "?" + query.toString() : "";
    return request<RMTotvsJobsResponse>("/api/v1/integrations/totvs-rm/jobs" + suffix);
  },

  totvsRmJob: (jobId: string) =>
    request<RMTotvsJobDetail>(`/api/v1/integrations/totvs-rm/jobs/${encodeURIComponent(jobId)}`),

  totvsRmMetrics: () =>
    request<RMTotvsMetrics>("/api/v1/integrations/totvs-rm/metrics"),

  enqueueTotvsRmSync: (body: {
    coligada_id: string; source_name: string; entity_name: string;
    schema_version?: string; page_size?: number; max_attempts?: number;
  }) => request<{ job_id: string; status: string; scope_id: string }>(
    "/api/v1/integrations/totvs-rm/sync",
    {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify(body),
    }
  ),

  cancelTotvsRmJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(
      `/api/v1/integrations/totvs-rm/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST" }
    ),

  retryTotvsRmJob: (jobId: string) =>
    request<{ id: string; status: string; manual_retry_number: number }>(
      `/api/v1/integrations/totvs-rm/jobs/${encodeURIComponent(jobId)}/retry`,
      { method: "POST" }
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
