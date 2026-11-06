import type { ReactNode } from "react";
import type { RecordIdentity } from "./record-types";

export function RecordHeading({ record, status, compact = false }: {
  record: RecordIdentity; status?: ReactNode; compact?: boolean;
}) {
  const initials = record.title.trim().split(/\s+/u).slice(0,2).map(part=>part[0] || "").join("").toLocaleUpperCase("pt-BR") || "•";
  return <div className="flex min-w-0 items-start gap-3">
    <span aria-hidden="true" className={"grid shrink-0 place-items-center rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-panel)] font-semibold text-[var(--color-slate-600)] " +
      (compact?"h-9 w-9 text-[length:var(--type-caption)]":"h-11 w-11 text-sm")}>{initials}</span>
    <div className="min-w-0 flex-1">
      <p className="text-[length:var(--type-overline)] font-medium uppercase tracking-[0.07em] text-[var(--color-muted)]">{record.caption || "Registro"}</p>
      <div className="mt-0.5 flex min-w-0 flex-wrap items-center gap-2">
        <h1 className={(compact?"text-[length:var(--type-heading-compact)]":"text-[length:var(--type-heading-medium)]")+" min-w-0 truncate font-semibold leading-tight tracking-[-0.028em] text-[var(--color-ink)]"}>{record.title}</h1>
        {status}
      </div>
      {record.subtitle && <p className="mt-1 truncate text-xs text-[var(--color-slate-600)]">{record.subtitle}</p>}
    </div>
  </div>;
}
