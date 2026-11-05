import { getAccessToken } from "./auth";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : "";

const ROOT = "/api/v1/native-academic/finance/payments";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  if (!token) throw new Error("Sessão institucional não encontrada.");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(BASE + path, {
    ...init, headers, cache: "no-store", credentials: "omit",
  });
  if (!res.ok) {
    let detail = res.status === 503 ? "Pagamentos em sandbox não habilitados."
      : res.status === 403 ? "Permissão insuficiente."
      : "Operação indisponível.";
    try {
      const data: { detail?: unknown } = await res.json();
      if (typeof data.detail === "string" && res.status !== 403) detail = data.detail;
    } catch { /* generic fallback */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}


export type AsaasDestination = {
  configured: boolean;
  status: "missing" | "pending" | "verified" | "rejected";
  wallet_id: string | null;
  version: number | null;
  receives_percent_of_net: 100;
  verified_for_live: boolean;
};

export type AsaasSplitPreview = {
  observation_id: string;
  student_id: string;
  source_profile_id: string;
  gross_charge_value: string;
  currency: "BRL";
  method_options: Array<"PIX" | "BOLETO">;
  split: Array<{ walletId: string; percentualValue: 100 }>;
  split_basis: "netValue";
  receives_percent_of_net: 100;
  recipient_verification: string;
  ready_for_real_charges: false;
  charge_created: false;
  settlement_confirmed: false;
};

export type SandboxProvider = {
  id: string; name: string; finance_profile_id: string;
  connection_kind: "composio" | "custom_pending";
  provider_slug: string; connected_account_id: string | null;
  methods: Array<"pix" | "boleto">; environment: "sandbox";
  enabled: boolean; revision: number; live_payments_enabled: false;
};

export type SandboxDraft = {
  id: string; provider_id: string; financial_observation_id: string;
  student_id: string; method: "pix" | "boleto"; amount: string;
  currency: "BRL"; status: "draft"; environment: "sandbox";
  payment_link: null; pix_code: null; boleto: null;
  settlement_confirmed: false; deduplicated: boolean;
};

export type FinancialObservation = {
  id: string; student_id: string; external_id: string;
  amount: string; paid_amount: string;
  canonical_state: string; raw_status: string;
};

export type SandboxEvidence = {
  event_id: string; state_reported: string;
  amount_reported: string; occurred_at: string;
};

function idempotency() {
  if (typeof crypto === "undefined" || !("randomUUID" in crypto)) {
    throw new Error("Navegador sem geração segura de identificadores.");
  }
  return crypto.randomUUID();
}

export const studentPaymentsApi = {
  asaasDestination: () => request<AsaasDestination>(ROOT + "/asaas/destination"),
  saveAsaasDestination: (walletId: string, expectedVersion: number | null) =>
    request<AsaasDestination>(ROOT + "/asaas/destination", {
      method: "PUT",
      body: JSON.stringify({ wallet_id: walletId, expected_version: expectedVersion,
        confirms_ownership: true }),
    }),
  previewAsaasSplit: (observationId: string) => request<AsaasSplitPreview>(
    ROOT + "/asaas/split-preview", {
      method: "POST",
      body: JSON.stringify({ financial_observation_id: observationId }),
    },
  ),
  providers: () => request<{ items: SandboxProvider[]; multiple_providers: boolean }>(ROOT + "/providers"),
  register: (payload: {
    finance_profile_id: string; name: string;
    connection_kind: "composio" | "custom_pending";
    provider_slug: string; methods: Array<"pix" | "boleto">;
  }) => request<SandboxProvider>(ROOT + "/providers", {
    method: "POST", body: JSON.stringify(payload),
  }),
  enable: (item: SandboxProvider, enabled: boolean) => request<SandboxProvider>(
    ROOT + `/providers/${encodeURIComponent(item.id)}/sandbox-enable`, {
      method: "PUT", body: JSON.stringify({ enabled, expected_revision: item.revision }),
    },
  ),
  drafts: () => request<{ items: SandboxDraft[]; live_payments_enabled: false }>(ROOT + "/drafts"),
  prepareDraft: (providerId: string, observationId: string, method: "pix" | "boleto") =>
    request<SandboxDraft>(ROOT + "/drafts", {
      method: "POST", headers: { "Idempotency-Key": idempotency() },
      body: JSON.stringify({ provider_id: providerId, financial_observation_id: observationId, method }),
    }),
  evidence: (draftId: string) => request<{
    items: SandboxEvidence[]; settlement_confirmed: false; evidence_source: "sandbox";
  }>(ROOT + `/drafts/${encodeURIComponent(draftId)}/events`),
  observations: (profileId: string) => request<{ items: FinancialObservation[]; settlement_confirmed: false }>(
    `/api/v1/native-academic/finance/reconciliation/profiles/${encodeURIComponent(profileId)}/observations`,
  ),
};
