import type { ObjectField, ObjectSort } from "./object-index-types";

/** Active clauses: legacy single-column view specs remain backwards compatible. */
export function activeSorts(state: { sort: ObjectSort | null; sorts?: ObjectSort[] }): ObjectSort[] {
  const candidates = state.sorts?.length ? state.sorts : state.sort ? [state.sort] : [];
  return candidates.filter((item, index) => candidates.findIndex(sort => sort.key === item.key) === index).slice(0, 3);
}

export function encodeSorts(sorts: ObjectSort[]): string {
  return sorts.slice(0, 3).map(item => item.key + ":" + (item.desc ? "desc" : "asc")).join(",");
}

export function sortObjectRows<T extends { id: string }>(
  rows: T[], fields: ObjectField<T>[], sorts: ObjectSort[],
): T[] {
  if (!sorts.length) return rows;
  const allowed = new Map(fields.filter(field => field.sortable).map(field => [field.key, field]));
  const clauses = sorts.filter(sort => allowed.has(sort.key)).slice(0, 3);
  return [...rows].sort((a, b) => {
    for (const { key, desc } of clauses) {
      const field = allowed.get(key)!;
      const av = field.getValue(a);
      const bv = field.getValue(b);
      if (av == null && bv == null) continue;
      if (av == null) return 1;
      if (bv == null) return -1;
      const diff = typeof av === "number" && typeof bv === "number"
        ? av - bv : String(av).localeCompare(String(bv), "pt-BR", { numeric: true });
      if (diff) return desc ? -diff : diff;
    }
    return a.id.localeCompare(b.id);
  });
}

/** Only a server-verified count may be presented as the global result count. */
export function verifiedCount(remote: boolean, partial: boolean, total?: number): number | null {
  if (!remote || partial || total === undefined || !Number.isSafeInteger(total) || total < 0) return null;
  return total;
}

export function pageSelection<T extends { id: string }>(
  rows: T[], selection: Record<string, boolean>,
): T[] {
  return rows.filter(row => selection[row.id] === true);
}
