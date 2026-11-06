import { getAccessToken, getApiKey } from "./auth";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : "";

export type CollectionCase = {
  id: string;
  external_ref: string;
  subject_type: "student" | "external";
  subject_ref: string;
  status: "open" | "paid" | "disputed" | "agreement" | "cancelled" | "unknown";
  balance: string | null;
  source: string;
  source_version: number;
  evidence_ref: string;
  verified_at: string | null;
  updated_at: string | null;
};

export type CollectionCasesPage = {
  items: CollectionCase[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type CollectionPaymentEvent = {
  id: string;
  source: string;
  source_event_id: string;
  source_version: number;
  amount_paid: string;
  obligation_status: string;
  remaining_balance: string | null;
  paid_at: string | null;
};

export type CollectionCaseDetail = {
  case: CollectionCase;
  payment_events: CollectionPaymentEvent[];
  payment_events_limited: boolean;
};

async function request<T>(path: string): Promise<T> {
  const headers = new Headers();
  const token = getAccessToken();
  const key = getApiKey();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (key) headers.set("X-API-Key", key);
  const response = await fetch(`${BASE}/api/v1/collections${path}`, { headers, cache: "no-store" });
  if (!response.ok) {
    let message = `Erro ${response.status}`;
    try {
      const data = await response.json() as { detail?: string };
      message = String(data.detail || message);
    } catch { /* Keep HTTP status. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const collectionsApi = {
  cases: ({ q = "", status = "", statuses, sort = "updated_at", sorts, filters, desc = true, limit = 25, offset = 0 }: {
    q?: string; status?: string; statuses?: string[]; sort?: string; sorts?: string; filters?: string; desc?: boolean; limit?: number; offset?: number;
  }): Promise<CollectionCasesPage> => {
    const params = new URLSearchParams({ q, limit: String(limit), offset: String(offset), sort, desc: String(desc) });
    if (sorts) params.set("sorts", sorts);
    if (filters) params.set("filters", filters);
    if (status) params.set("status", status);
    if (statuses?.length) params.set("statuses", statuses.join(","));
    return request<CollectionCasesPage>(`/cases?${params.toString()}`);
  },
  detail: (id: string): Promise<CollectionCaseDetail> =>
    request<CollectionCaseDetail>(`/cases/${encodeURIComponent(id)}`),
};
