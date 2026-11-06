import type { RecordIdentity } from "./record-types";
import { ChevronRight } from "@/components/ui/icons";

export function RecordPreview({ record, detail, onOpen }: {
  record: RecordIdentity; detail?: string | null; onOpen?: () => void;
}) {
  const inner = <><span className="grid h-8 w-8 shrink-0 place-items-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] text-[11px] font-semibold" aria-hidden="true">
    {record.title.trim().slice(0, 2).toLocaleUpperCase("pt-BR")}
  </span><span className="min-w-0 flex-1 text-left">
    <span className="block truncate text-[12px] font-semibold">{record.title}</span>
    {record.subtitle && <span className="block truncate text-[11px] text-[var(--color-muted)]">{record.subtitle}</span>}
    {detail && <span className="block truncate text-[11px] text-[var(--color-slate-600)]">{detail}</span>}
  </span>{onOpen && <ChevronRight className="h-4 w-4 shrink-0 text-[var(--color-muted)]" aria-hidden="true" />}</>;
  const classes="flex w-full items-center gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 py-3 text-[var(--color-ink)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] motion-reduce:transition-none";
  return onOpen ? <button type="button" onClick={onOpen} className={classes} aria-label={"Abrir " + record.title}>{inner}</button>
    : <div className={classes}>{inner}</div>;
}
