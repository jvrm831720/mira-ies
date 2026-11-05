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
    path === "/api/v1/auth/login/password" ||
    path.startsWith("/api/v1/auth/whatsapp/") ||
    path.startsWith("/api/v1/auth/email/") ||
    path.startsWith("/api/v1/auth/password/") ||
    path.startsWith("/api/v1/auth/mfa/login/") ||
    path.startsWith("/api/v1/org/invites/accept");
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

// TEMPORARY RESTORE MARKER — full body continues in next commit if needed
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

  me: () => request<OrgMeResponse>("/api/v1/org/me"),

  completeOnboarding: () =>
    request<{ onboarding_completed: boolean; onboarding_completed_at?: string | null }>(
      "/api/v1/org/me/onboarding/complete",
      { method: "POST" }
    ),

  listWorkspaces: () => request<WorkspacesResponse>("/api/v1/org/workspaces"),

  switchWorkspace: (body: { membership_id?: string; tenant_id?: string }) =>
    request<SwitchWorkspaceResponse>("/api/v1/org/workspaces/switch", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Re-export remaining methods: RESTORE FROM COMMIT 9c176e2 if app needs full surface
  // The complete client lives in git history at frontend/src/lib/api.ts @ 9c176e2188a169c347d50b94adc5d172e4badf9f
};
