import type { ReactNode } from "react";

export type ObjectKind = "students" | "campaigns" | "academic_classes" | "academic_programs" | "academic_subjects" | "academic_teachers" | "academic_terms" | "collections";
export type PropertyType = "text" | "number" | "currency" | "percentage" | "date" |
  "datetime" | "status" | "select" | "multiselect" | "person" | "reference" | "boolean" | "identifier";

export type FilterOperator =
  "contains" | "not_contains" | "eq" | "neq" | "starts_with" |
  "gt" | "lt" | "between" | "in" | "before" | "after" | "empty";

export type ObjectFilter = { key: string; op: FilterOperator; value: string | number | Array<string | number> | null };
export type ObjectSort = { key: string; desc: boolean };
export type ObjectViewSpec = {
  version: 1;
  filters: ObjectFilter[];
  sort: ObjectSort | null;
  sorts?: ObjectSort[];
  density?: "compact" | "comfortable";
  pinned?: string[];
  columnWidths?: Record<string, number>;
  columns: string[];
  page_size: 25 | 50 | 100;
};
export type SavedObjectView = {
  id: string;
  object_key: ObjectKind;
  name: string;
  scope: "personal";
  config: ObjectViewSpec;
  version: 1;
  created_at: string;
  updated_at: string;
};

export type ObjectField<T> = {
  key: string;
  title: string;
  type: PropertyType;
  getValue: (record: T) => unknown;
  render?: (record: T) => ReactNode;
  primary?: boolean;
  sensitive?: boolean;
  filterable?: boolean;
  sortable?: boolean;
  width?: number;
  options?: Array<{ value: string; label: string }>;
  nullLabel?: "—" | "Não informado" | "Desconhecido";
};

export type ObjectDefaultView = {
  id: string;
  title: string;
  /** Domain-aware selector interpreted by the API adapter, not arbitrary SQL. */
  filterKey?: string;
};

export function defaultViewSpec<T>(fields: ObjectField<T>[]): ObjectViewSpec {
  return {
    version: 1, filters: [], sort: null, sorts: [], density: "comfortable", pinned: [], columnWidths: {},
    columns: fields.map(field => field.key),
    page_size: 50,
  };
}

export function validateObjectView<T>(fields: ObjectField<T>[], spec: ObjectViewSpec): ObjectViewSpec {
  const allowed = new Map(fields.map(field => [field.key, field]));
  const columns = spec.columns.filter((key, index) => allowed.has(key) && spec.columns.indexOf(key) === index);
  for (const field of fields) if (field.primary && !columns.includes(field.key)) columns.unshift(field.key);
  return {
    version: 1,
    filters: spec.filters.filter(filter => allowed.get(filter.key)?.filterable).slice(0, 8),
    sort: spec.sort && allowed.get(spec.sort.key)?.sortable ? spec.sort : null,
    sorts: (spec.sorts || (spec.sort ? [spec.sort] : []))
      .filter((item, i, source) => allowed.get(item.key)?.sortable && source.findIndex(s => s.key === item.key) === i)
      .slice(0, 3),
    density: spec.density === "compact" ? "compact" : "comfortable",
    pinned: (spec.pinned || []).filter((key, index, all) => allowed.has(key) &&
      columns.includes(key) && all.indexOf(key) === index).slice(0, 3),
    columnWidths: Object.fromEntries(Object.entries(spec.columnWidths || {}).filter(([key, width]) =>
      allowed.has(key) && columns.includes(key) && Number.isFinite(width) && width >= 100 && width <= 640)),
    columns,
    page_size: [25, 50, 100].includes(spec.page_size) ? spec.page_size : 50,
  };
}
