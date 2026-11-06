import type { ObjectFilter, ObjectField, FilterOperator } from "./object-index-types";

/** Safe client-only filter evaluation for bounded preview data.
 * Server-backed indices must apply filters on the server instead. */
export const FILTER_OPS: Record<string, Array<{ value: FilterOperator; label: string }>> = {
  text: [
    { value: "contains", label: "Contém" }, { value: "not_contains", label: "Não contém" },
    { value: "eq", label: "É igual" }, { value: "starts_with", label: "Começa com" },
    { value: "empty", label: "Está vazio" },
  ],
  number: [
    { value: "eq", label: "Igual" }, { value: "gt", label: "Maior que" },
    { value: "lt", label: "Menor que" }, { value: "between", label: "Entre" },
    { value: "empty", label: "Está vazio" },
  ],
  select: [
    { value: "eq", label: "É" }, { value: "neq", label: "Não é" },
    { value: "in", label: "Está em uma seleção" }, { value: "empty", label: "Está vazio" },
  ],
  date: [
    { value: "before", label: "Antes" }, { value: "after", label: "Depois" },
    { value: "between", label: "Entre" }, { value: "empty", label: "Está vazio" },
  ],
  boolean: [{ value: "eq", label: "Sim" }, { value: "neq", label: "Não" }],
};
FILTER_OPS.status = FILTER_OPS.select;
FILTER_OPS.percentage = FILTER_OPS.number;
FILTER_OPS.currency = FILTER_OPS.number;
FILTER_OPS.datetime = FILTER_OPS.date;
FILTER_OPS.identifier = FILTER_OPS.text;
FILTER_OPS.person = FILTER_OPS.text;
FILTER_OPS.reference = FILTER_OPS.text;

function coerceDate(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const t = Date.parse(value);
  return Number.isFinite(t) ? t : null;
}
export function matchesObjectFilters<T>(record: T, fields: ObjectField<T>[], filters: ObjectFilter[]): boolean {
  const map = new Map(fields.map(field => [field.key, field]));
  return filters.every(filter => {
    const field = map.get(filter.key);
    if (!field?.filterable) return false;
    const raw = field.getValue(record);
    if (filter.op === "empty") return raw == null || raw === "";
    if (raw == null || filter.value == null) return false;
    const string = String(raw).toLocaleLowerCase("pt-BR");
    const expected = String(filter.value).toLocaleLowerCase("pt-BR");
    if (filter.op === "contains") return string.includes(expected);
    if (filter.op === "not_contains") return !string.includes(expected);
    if (filter.op === "starts_with") return string.startsWith(expected);
    if (filter.op === "eq") return String(raw) === String(filter.value);
    if (filter.op === "neq") return String(raw) !== String(filter.value);
    if (filter.op === "in") return Array.isArray(filter.value) && filter.value.map(String).includes(String(raw));
    const left = field.type === "date" || field.type === "datetime" ? coerceDate(raw) : Number(raw);
    const values = Array.isArray(filter.value) ? filter.value : [filter.value];
    const numbers = values.map(value => field.type === "date" || field.type === "datetime" ? coerceDate(value) : Number(value));
    if (left == null || !Number.isFinite(left) || numbers.some(value => value == null || !Number.isFinite(value))) return false;
    if (filter.op === "gt" || filter.op === "after") return left > numbers[0]!;
    if (filter.op === "lt" || filter.op === "before") return left < numbers[0]!;
    if (filter.op === "between") return numbers.length === 2 && left >= numbers[0]! && left <= numbers[1]!;
    return false;
  });
}
export function formatPropertyValue(type: string, value: unknown, nullLabel = "—"): string {
  if (value === null || value === undefined || value === "") return nullLabel;
  if (type === "boolean") return value === true ? "Sim" : value === false ? "Não" : nullLabel;
  if (type === "multiselect") return Array.isArray(value) ? value.map(String).join(", ") || nullLabel : nullLabel;
  if (type === "number" || type === "percentage" || type === "currency") {
    if (typeof value !== "number" || !Number.isFinite(value)) return nullLabel;
    if (type === "currency") return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
    return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value) + (type === "percentage" ? "%" : "");
  }
  if (type === "date" || type === "datetime") {
    if (typeof value !== "string") return nullLabel;
    // Date-only values have no timezone and must not be shifted to the previous day.
    const d = type === "date" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(value + "T12:00:00Z") : new Date(value);
    if (Number.isNaN(d.getTime())) return nullLabel;
    const fmt = type === "date"
      ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeZone: "UTC" })
      : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" });
    return fmt.format(d);
  }
  return String(value);
}
