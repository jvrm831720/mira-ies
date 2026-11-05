import { getAccessToken, getApiKey } from "./auth";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  const key = getApiKey();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (key) headers.set("X-API-Key", key);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${BASE}/api/v1/dispatch${path}`, { ...init, headers });
  if (!response.ok) {
    let reason = response.statusText;
    try {
      const data = await response.json() as { detail?: string };
      reason = String(data.detail || reason);
    } catch { /* keep status text */ }
    throw new Error(reason || `Erro ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type DispatchCampaign = {
  id: string;
  name: string;
  purpose: "retention" | "academic" | "service" | "collections";
  delivery_mode: "individual" | "targeted" | "bulk";
  channel: "email" | "sms" | "whatsapp";
  status: "draft" | "approved" | "scheduled" | "running" | "paused" | "completed" | "cancelled";
  template_ref: string;
  created_at: string;
  scheduled_for: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
  paused_reason: string | null;
  total: number;
  pending: number;
  accepted: number;
  simulated: number;
  problems: number;
  replied: number;
};
export type DispatchMetrics = {
  campaigns: number; queued: number; accepted: number;
  worker_online?: boolean; worker_last_seen?: string | null;
  estimated_cost_brl?: number;
  simulated: number; problems: number; replies: number; note: string;
};
export type DispatchPaymentResults = {
  payments: { transactions: number; received_brl: number };
  obligations: Record<string, number>;
  note: string;
};
export type CampaignDraft = {
  name: string; purpose: "retention" | "academic" | "service" | "collections";
  delivery_mode: "targeted" | "bulk";
  channel: "email" | "sms" | "whatsapp";
  template_ref: string; template_body: string;
  per_minute_limit?: number;
};

export type DispatchTemplate = {
  id: string; code: string; version: number;
  purpose: "retention" | "academic" | "service" | "collections";
  channel: "email" | "sms" | "whatsapp";
  subject: string; status: "draft" | "approved" | "retired";
  created_by: string; approved_by: string | null;
  approved_at: string | null;
};
export type DispatchProviderAccount = {
  provider: "resend" | "twilio"; status: "active" | "disabled";
  configured_at: string; credential_version: number;
  last_verified_at: string | null;
};
export type IndividualIntervention = {
  template_id: string; subject_type: "student" | "external";
  subject_ref: string; evidence_ref: string; scheduled_for?: string;
};

export const dispatchApi = {
  templates: () => request<{ items: DispatchTemplate[] }>("/templates"),
  createTemplate: (data: {
    code: string; purpose: DispatchTemplate["purpose"];
    channel: DispatchTemplate["channel"]; subject: string; body: string;
  }) => request<{ id: string; status: string }>("/templates", {
    method: "POST", body: JSON.stringify(data),
  }),
  approveTemplate: (id: string, evidenceRef: string) =>
    request<{ id: string; status: string }>(
      `/templates/${encodeURIComponent(id)}/approve`,
      { method: "POST", body: JSON.stringify({ evidence_ref: evidenceRef }) },
    ),
  intervene: (data: IndividualIntervention, idempotencyKey: string) =>
    request<{ id: string; status: string; deduplicated: boolean }>(
      "/interventions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(data),
      },
    ),
  providers: () => request<{ items: DispatchProviderAccount[] }>("/providers"),
  configureProvider: (provider: "resend" | "twilio", credentials: Record<string, string>) =>
    request<DispatchProviderAccount>(`/providers/${provider}`, {
      method: "PUT", body: JSON.stringify({ credentials }),
    }),
  verifyProvider: (provider: "resend" | "twilio") =>
    request<{ verified: boolean }>(`/providers/${provider}/verify`, { method: "POST" }),
  activateProvider: (provider: "resend" | "twilio", evidenceRef: string) =>
    request<{ status: string }>(`/providers/${provider}/activate`, {
      method: "POST", body: JSON.stringify({ evidence_ref: evidenceRef }),
    }),
  disableProvider: (provider: "resend" | "twilio") =>
    request<{ status: string }>(`/providers/${provider}/disable`, { method: "POST" }),
  campaigns: () => request<{ items: DispatchCampaign[] }>("/campaigns"),
  metrics: () => request<DispatchMetrics>("/metrics"),
  financial: () => request<DispatchPaymentResults>("/recovery/summary"),
  create: (data: CampaignDraft) =>
    request<DispatchCampaign>("/campaigns", { method: "POST", body: JSON.stringify(data) }),
  stage: (campaignId: string, targets: Array<{
    subject_type: "student" | "external"; subject_ref: string;
    consent_ref: string; obligation_ref?: string;
  }>) => request<{ created: number; duplicates: number }>(
    `/campaigns/${encodeURIComponent(campaignId)}/targets`,
    { method: "POST", body: JSON.stringify({ targets }) },
  ),
  stageProposal: (campaignId: string, proposalId: string) =>
    request<{ created: number; duplicates: number }>(
      `/campaigns/${encodeURIComponent(campaignId)}/targets/from-proposal`,
      { method: "POST", body: JSON.stringify({ proposal_id: proposalId }) },
    ),
  approve: (id: string, reference: string) => request<DispatchCampaign>(
    `/campaigns/${encodeURIComponent(id)}/approve`,
    { method: "POST", body: JSON.stringify({ authorization_ref: reference }) },
  ),
  action: (id: string, action: "start" | "pause" | "resume" | "cancel") =>
    request<DispatchCampaign>(
      `/campaigns/${encodeURIComponent(id)}/${action}`,
      { method: "POST" },
    ),
  schedule: (id: string, date: string) =>
    request<DispatchCampaign>(
      `/campaigns/${encodeURIComponent(id)}/schedule`,
      { method: "POST", body: JSON.stringify({ scheduled_for: date }) },
    ),
  replies: (id: string) => request<{ items: Array<{
    event_kind: string; reply_intent: string | null; recommended_action: string | null;
    occurred_at: string;
  }> }>(`/campaigns/${encodeURIComponent(id)}/replies`),
};
