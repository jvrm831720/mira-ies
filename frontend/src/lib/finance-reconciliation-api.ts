import { getAccessToken } from "./auth";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : "";

const ROOT = "/api/v1/native-academic/finance/reconciliation";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  if (!token) throw new Error("É necessária uma sessão institucional com MFA.");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init, headers, cache: "no-store", credentials: "omit",
  });
  if (!res.ok) {
    const defaultMessage = res.status === 503
      ? "Conciliação ainda não ativada para este workspace."
      : res.status === 403 ? "Permissão insuficiente. Consulte seu administrador."
        : res.status === 401 ? "Sua sessão expirou." : "Operação indisponível.";
    let reason = defaultMessage;
    try {
      const data: { detail?: unknown } = await res.json();
      if (typeof data.detail === "string" && res.status !== 403) reason = data.detail;
    } catch { /* generic fallback */ }
    throw new Error(reason);
  }
  return res.json() as Promise<T>;
}

export type FinanceFieldMap = Record<string, string>;
export type ReviewWorkflow = {
  transitions: Record<string, string[]>;
  labels: Record<string, string>;
};

export type FinanceProfile = {
  id: string;
  name: string;
  source_kind: "composio" | "import";
  connected_account_id: string | null;
  tool_slug: string | null;
  rows_path: string;
  field_map: FinanceFieldMap;
  status_map: Record<string, string>;
  student_lookup: "mira_id" | "verified_external";
  review_workflow: ReviewWorkflow;
  enabled: boolean;
  mapping_version: number;
  created_at: string;
};

export type ProfilePayload = Omit<FinanceProfile, "id" | "enabled" | "mapping_version" | "created_at">;
export type FinanceConnection = {
  connected_account_id: string;
  toolkit_slug: string;
  display_name: string | null;
  status: string;
  disconnected_at?: string | null;
};
export type FinanceComposioTool = { slug: string; description?: string };
export type Discrepancy = {
  student_id: string;
  correlation_key: string;
  sources: number;
  observations: number;
  result: "conflict" | "multi_source_consistent" | "single_source";
  items: Array<{ profile_id: string; external_id: string; state: string; amount: string; paid_amount: string }>;
  settlement_confirmed: false;
};

const identityKey = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  throw new Error("Idempotência segura não disponível neste navegador.");
};

export const financeApi = {
  profiles: () => request<{ items: FinanceProfile[] }>(ROOT + "/profiles"),
  create: (payload: ProfilePayload) => request<FinanceProfile>(
    ROOT + "/profiles", { method: "POST", body: JSON.stringify(payload) },
  ),
  update: (p: FinanceProfile, enabled: boolean) => request<FinanceProfile>(
    ROOT + `/profiles/${encodeURIComponent(p.id)}`, {
      method: "PUT",
      body: JSON.stringify({
        expected_version: p.mapping_version, name: p.name, rows_path: p.rows_path,
        field_map: p.field_map, status_map: p.status_map,
        review_workflow: p.review_workflow, student_lookup: p.student_lookup,
        enabled,
      }),
    },
  ),
  connections: () => request<{ items: FinanceConnection[] }>("/api/v1/integrations/composio/connections"),
  financialCatalog: () => request<{ items: Array<{ slug: string; composio_toolkits?: Array<{ slug: string }> }> }>(
    "/api/v1/integrations/composio/catalog/categories",
  ),
  tools: (slug: string) => request<{ items: FinanceComposioTool[] }>(
    `/api/v1/integrations/composio/catalog/${encodeURIComponent(slug)}/tools`
  ),
  preview: (profileId: string, rows: Record<string, unknown>[]) => request<{
    total: number; students_linked: boolean; states: Record<string, number>;
    persisted: false; settlement_confirmed: false;
  }>(ROOT + `/profiles/${profileId}/preview`, {
    method: "POST", body: JSON.stringify({ rows }),
  }),
  csvImport: (profileId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ batch_id: string; imported: number; unchanged: number; settlement_confirmed: false }>(
      ROOT + `/profiles/${profileId}/import-csv`, {
        method: "POST", headers: { "Idempotency-Key": identityKey() }, body: form,
      }
    );
  },
  composioSync: (profileId: string, args: Record<string, unknown>) => request<{
    batch_id: string; imported: number; unchanged: number; settlement_confirmed: false;
  }>(ROOT + `/profiles/${profileId}/sync`, {
    method: "POST",
    headers: { "Idempotency-Key": identityKey() },
    body: JSON.stringify({ arguments: args }),
  }),
  linkStudent: (profileId: string, externalRef: string, studentId: string) => request<{
    profile_id: string; student_id: string; already_linked: boolean;
  }>(ROOT + `/profiles/${profileId}/student-links`, {
    method: "POST", body: JSON.stringify({
      external_student_ref: externalRef, student_id: studentId,
    }),
  }),
  discrepancies: () => request<{ items: Discrepancy[]; total_groups_examined: number }>(
    ROOT + "/discrepancies",
  ),
  review: (profileId: string, externalId: string, note: string) => request<{
    id: string; step: string; version: number;
  }>(ROOT + `/profiles/${profileId}/review-cases`, {
    method: "POST", body: JSON.stringify({ external_id: externalId, note }),
  }),
  transition: (caseId: string, expectedVersion: number, step: string, note: string) =>
    request<{ id: string; step: string; version: number }>(
      ROOT + `/review-cases/${caseId}/transition`, {
        method: "POST", body: JSON.stringify({ expected_version: expectedVersion, step, note }),
      },
    ),
};
