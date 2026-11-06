import { getAccessToken } from "./auth";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : "";
const ROOT = "/api/v1/native-academic/finance/asaas";

export type AsaasCharge = {
  id: string; student_id: string; financial_observation_id: string;
  method: "pix" | "boleto"; amount: string; currency: "BRL";
  due_date: string; environment: "sandbox" | "production";
  creation_state: "prepared" | "submitting" | "unknown" | "created" | "rejected" | "review";
  payment_status: string; split_status: string;
  payment_received_verified: boolean; split_settled_verified: boolean;
  needs_review: boolean; destination_wallet_id: string; split_percent_of_net: 100;
};

async function call<T>(path: string, method = "GET", payload?: Record<string, unknown>): Promise<T> {
  const access = getAccessToken();
  if (!access) throw new Error("É necessária uma sessão institucional.");
  const result = await fetch(BASE + ROOT + path, {
    method, cache: "no-store", credentials: "omit",
    headers: { Authorization: `Bearer ${access}`, ...(payload ? { "Content-Type": "application/json" } : {}) },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!result.ok) {
    let message = "Operação indisponível.";
    try {
      const data: { detail?: unknown } = await result.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch { /* fallback */ }
    throw new Error(message);
  }
  return result.json() as Promise<T>;
}

export const asaasApi = {
  readiness: () => call<{ enabled: boolean; environment: string; production: boolean; split_percent_of_net?: number }>("/health"),
  charges: () => call<{ items: AsaasCharge[] }>("/charges"),
  prepare: (observationId: string, method: "pix" | "boleto", dueDate: string) => call<AsaasCharge>(
    "/charges/prepare", "POST", { financial_observation_id: observationId, method, due_date: dueDate },
  ),
  issue: (chargeId: string) => call<AsaasCharge>(
    `/charges/${encodeURIComponent(chargeId)}/issue`, "POST", { confirms_issue: true },
  ),
  reconcile: (chargeId: string) => call<AsaasCharge>(
    `/charges/${encodeURIComponent(chargeId)}/reconcile`, "POST",
  ),
  verifyWallet: (evidenceReference: string) => call<{ verified: true }>(
    "/destination/verify", "POST", { evidence_reference: evidenceReference },
  ),
  events: () => call<{ items: Array<{ event_id: string; event_type: string; charge_id: string; received_at: string }> }>("/webhook-events"),
};
