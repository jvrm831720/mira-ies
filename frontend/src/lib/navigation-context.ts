import type { ObjectField, ObjectDefaultView, ObjectFilter } from "@/components/object-index/object-index-types";
import type { ObjectIndexState } from "@/components/object-index/object-index";

/** Wave 1: presentation-only URL state. No record payload or authorization data is stored here. */
const KEYS = ["v", "q", "f", "sort", "cols", "page", "size", "record"] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FILTER_OPERATORS = new Set([
  "eq", "neq", "contains", "not_contains", "starts_with", "gt", "lt",
  "between", "in", "before", "after", "empty",
]);
const OP_BY_TYPE: Record<string, Set<string>> = {
  number: new Set(["eq", "gt", "lt", "between", "empty"]),
  percentage: new Set(["eq", "gt", "lt", "between", "empty"]),
  currency: new Set(["eq", "gt", "lt", "between", "empty"]),
  status: new Set(["eq", "neq", "in", "empty"]),
  select: new Set(["eq", "neq", "in", "empty"]),
  date: new Set(["before", "after", "between", "empty"]),
  datetime: new Set(["before", "after", "between", "empty"]),
};

function safeFilterValue(value: unknown): value is ObjectFilter["value"] {
  if (value === null) return true;
  if (typeof value === "string") return value.length <= 160;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.length > 0 && value.length <= 12 &&
    value.every(part => (typeof part === "string" && part.length <= 160) ||
      (typeof part === "number" && Number.isFinite(part)));
  return false;
}

function parseFilters<T>(raw: string | null, fields: ObjectField<T>[]): ObjectFilter[] {
  if (!raw || raw.length > 2000) return [];
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return []; }
  if (!Array.isArray(parsed)) return [];
  const allowed = new Map(fields.filter(field => field.filterable).map(field => [field.key, field]));
  return parsed.slice(0, 8).filter((item): item is ObjectFilter => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const value = item as Record<string, unknown>;
    const field = typeof value.key === "string" ? allowed.get(value.key) : undefined;
    if (!field || typeof value.op !== "string" || !FILTER_OPERATORS.has(value.op) ||
      !(OP_BY_TYPE[field.type] || FILTER_OPERATORS).has(value.op)) return false;
    return safeFilterValue(value.value) && (value.op !== "empty" || value.value === null);
  });
}

export function readRecordId(search: URLSearchParams): string | null {
  const id = search.get("record");
  return id && UUID.test(id) ? id : null;
}

export function readObjectIndexState<T>(
  search: URLSearchParams,
  fields: ObjectField<T>[],
  views: ObjectDefaultView[],
  fallback: ObjectIndexState,
): ObjectIndexState {
  const state: ObjectIndexState = { ...fallback, filters: [...fallback.filters], columns: [...fallback.columns] };
  const view = search.get("v") || search.get("tab");
  if (view && views.some(item => item.id === view)) state.view = view;
  state.query = (search.get("q") || "").slice(0, 160);
  state.filters = parseFilters(search.get("f"), fields);
  // Compatibility with legacy /alunos?risk=critico links.
  if (!search.has("f") && fields.some(field => field.key === "risk_level" && field.filterable)) {
    const risk = search.get("risk");
    if (risk && ["critico", "medio", "baixo"].includes(risk)) {
      state.filters = [{ key: "risk_level", op: "eq", value: risk }];
    }
  }
  const sort = search.get("sort") || "";
  const [sortKey, direction] = sort.split(":");
  if (["asc", "desc"].includes(direction) && fields.some(field => field.key === sortKey && field.sortable)) {
    state.sort = { key: sortKey, desc: direction === "desc" };
  }
  const columns = search.get("cols");
  if (columns !== null && columns.length <= 800) {
    const permitted = new Set(fields.map(field => field.key));
    const list = [...new Set(columns.split(",").filter(key => permitted.has(key)))];
    for (const field of fields) if (field.primary && !list.includes(field.key)) list.unshift(field.key);
    if (list.length) state.columns = list;
  }
  const page = Number(search.get("page"));
  if (Number.isInteger(page) && page >= 0 && page <= 10000) state.pageIndex = page;
  const size = Number(search.get("size"));
  if (size === 25 || size === 50 || size === 100) state.pageSize = size;
  return state;
}

/** Retains unrelated route parameters (e.g. import source) and removes obsolete legacy keys. */
export function buildIndexHref(
  pathname: string, source: URLSearchParams, state: ObjectIndexState, recordId: string | null,
): string {
  const params = new URLSearchParams(source);
  for (const key of KEYS) params.delete(key);
  params.delete("tab");
  params.delete("risk");
  if (state.view !== "todos") params.set("v", state.view);
  if (state.query) params.set("q", state.query.slice(0, 160));
  if (state.filters.length) {
    const filters = JSON.stringify(state.filters.slice(0, 8));
    if (filters.length <= 2000) params.set("f", filters);
  }
  if (state.sort) params.set("sort", state.sort.key + ":" + (state.sort.desc ? "desc" : "asc"));
  if (state.columns.length && state.columns.join(",").length <= 800) {
    params.set("cols", state.columns.join(","));
  }
  if (state.pageIndex > 0) params.set("page", String(Math.min(state.pageIndex, 10000)));
  if (state.pageSize !== 50) params.set("size", String(state.pageSize));
  if (recordId && UUID.test(recordId)) params.set("record", recordId);
  const query = params.toString();
  return pathname + (query ? "?" + query : "");
}

/** A full-page student link accepts only an internal /alunos listing as its return target. */
export function studentReturnHref(candidate: string | null): string {
  if (!candidate || candidate.length > 9000 || !candidate.startsWith("/alunos")) return "/alunos";
  try {
    const parsed = new URL(candidate, "https://mira.invalid");
    if (parsed.origin !== "https://mira.invalid" || parsed.pathname !== "/alunos" || parsed.hash) return "/alunos";
    parsed.searchParams.delete("record");
    parsed.searchParams.delete("from");
    return parsed.pathname + parsed.search;
  } catch { return "/alunos"; }
}

export function studentDetailHref(id: string, listingHref: string): string {
  const base = "/alunos/" + encodeURIComponent(id);
  const back = studentReturnHref(listingHref);
  return back === "/alunos" ? base : base + "?from=" + encodeURIComponent(back);
}

/** Short hash for session-only scroll positions; never persist search terms as storage keys. */
export function navigationFingerprint(scope: string, href: string): string {
  let hash = 2166136261;
  for (const char of scope + "|" + href) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}
