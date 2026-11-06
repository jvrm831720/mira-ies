import { getAccessToken, getApiKey } from "@/lib/auth";
import type { ObjectKind, ObjectViewSpec, SavedObjectView } from "@/components/object-index/object-index-types";

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000" : "";

export type ObjectIndexStudent = {
  id: string;
  nome: string;
  matricula?: string | null;
  curso?: string | null;
  risk_level?: string | null;
  risk_score?: number | null;
  shap_summary?: string | null;
  follow_up?: { status: string; created_at: string | null } | null;
};
export type StudentIndexResponse = {
  students: ObjectIndexStudent[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  scope: "tenant";
};
export type StudentIndexParams = {
  limit: number; offset: number; q?: string; risk_level?: string;
  course?: string; sort?: string; view?: string;
  filters?: ObjectViewSpec["filters"];
  sorts?: string;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  const key = getApiKey();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", "Bearer " + token);
  else if (key) headers.set("X-API-Key", key);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(BASE + path, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "Falha ao carregar dados.");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** A separate endpoint preserves the old /students response and consumers. */
export function listStudentIndex(params: StudentIndexParams): Promise<StudentIndexResponse> {
  const q = new URLSearchParams();
  q.set("limit", String(params.limit));
  q.set("offset", String(params.offset));
  if (params.q) q.set("q", params.q);
  if (params.risk_level) q.set("risk_level", params.risk_level);
  if (params.course) q.set("course", params.course);
  if (params.sort) q.set("sort", params.sort);
  if (params.sorts) q.set("sorts", params.sorts);
  if (params.view) q.set("view", params.view);
  if (params.filters?.length) q.set("filters", JSON.stringify(params.filters));
  return request("/api/v1/object-index/students?" + q.toString());
}
export function listSavedObjectViews(object: ObjectKind): Promise<{ views: SavedObjectView[] }> {
  return request("/api/v1/object-views?object_key=" + object);
}
export function createSavedObjectView(object: ObjectKind, name: string, config: ObjectViewSpec): Promise<SavedObjectView> {
  return request("/api/v1/object-views", {
    method: "POST", body: JSON.stringify({ object_key: object, name, scope: "personal", config }),
  });
}
export function updateSavedObjectView(id: string, name: string, config: ObjectViewSpec): Promise<SavedObjectView> {
  return request("/api/v1/object-views/" + encodeURIComponent(id), {
    method: "PUT", body: JSON.stringify({ name, config }),
  });
}
export function deleteSavedObjectView(id: string): Promise<void> {
  return request("/api/v1/object-views/" + encodeURIComponent(id), { method: "DELETE" });
}
