import { getAccessToken } from "./auth";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : "";
const ROOT = "/api/v1/native-academic/finance/payments";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  if (!token) throw new Error("É necessário entrar como operador institucional.");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(BASE + path, { ...init, headers, cache: "no-store", credentials: "omit" });
  if (!response.ok) {
    let reason = response.status === 503 ? "Preparação de pagamentos ainda não ativada."
      : response.status === 403 ? "MFA e permissão institucional são necessários."
        : "Não foi possível concluir a operação.";
    if (response.status !== 403) {
      try { const body: { detail?: unknown } = await response.json();
        if (typeof body.detail === "string") reason = body.detail;
      } catch { /* generic error */ }
    }
    throw new Error(reason);
  }
  return response.json() as Promise<T>;
}

export type PaymentConnector = {
  id: string; name: string; provider_slug: "asaas";
  destination_wallet_id: string; destination_verification_status: "pending" | "verified" | "blocked";
  split_percentual_value: 100; split_basis: "netValue";
  mode: "sandbox"; enabled: boolean; configuration_version: number;
  payment_execution_enabled: false;
};
export type PaymentProposal = {
  id: string; connector_id: string; observation_id: string; student_id: string;
  source_profile_id: string; source_external_id: string;
  amount: string; currency: "BRL"; status: "draft" | "awaiting_approval" | "approved" | "cancelled";
  created_at: string; approved_at: string | null; provider_execution_enabled: false;
  settlement_confirmed: false; checkout_url: null; pix: null; boleto: null;
};
export type PaymentObservation = {
  id: string; student_id: string; external_id: string; amount: string;
  paid_amount: string; canonical_state: string; raw_status: string;
};
export const paymentPreparationApi = {
  connectors: () => request<{ items: PaymentConnector[] }>(ROOT + "/connectors"),
  createConnector: (data: { destination_wallet_id: string }) =>
    request<PaymentConnector>(ROOT + "/connectors", { method: "POST", body: JSON.stringify(data) }),
  toggleConnector: (p: PaymentConnector, enabled: boolean) =>
    request<PaymentConnector>(ROOT + `/connectors/${p.id}`, {
      method: "PUT", body: JSON.stringify({ expected_version: p.configuration_version, enabled }),
    }),
  orders: () => request<{ items: PaymentProposal[] }>(ROOT + "/orders"),
  observations: (profile: string) => request<{ items: PaymentObservation[] }>(
    `/api/v1/native-academic/finance/reconciliation/profiles/${profile}/observations`),
  prepare: (connectorId: string, observationId: string) => {
    if (typeof crypto === "undefined" || !("randomUUID" in crypto))
      throw new Error("Idempotência segura indisponível.");
    return request<PaymentProposal>(ROOT + "/orders", {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ connector_id: connectorId, observation_id: observationId }),
    });
  },
  review: (proposal: PaymentProposal, target: "awaiting_approval" | "approved" | "cancelled", note: string) =>
    request<PaymentProposal>(ROOT + `/orders/${proposal.id}/review`, {
      method: "POST",
      body: JSON.stringify({ expected_status: proposal.status, target, note }),
    }),
};
