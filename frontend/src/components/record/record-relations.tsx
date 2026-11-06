import Link from "next/link";
import type { RecordRelation } from "./record-types";
import { ChevronRight } from "@/components/ui/icons";

export function RecordRelations({ relations, empty = "Nenhum vínculo disponível nesta consulta." }: {
  relations: RecordRelation[]; empty?: string;
}) {
  return <section aria-label="Relações" className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
    <h3 className="border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2.5 text-[11px] font-semibold text-[var(--color-slate-600)]">Relações</h3>
    {relations.length ? <ul className="divide-y divide-[var(--color-border-subtle)]">{relations.map(item => <li key={item.id}>
      {item.href ? <Link href={item.href}
        className="flex items-center justify-between gap-3 px-4 py-3 text-[12px] hover:bg-[var(--color-panel)]">
        <span className="text-[var(--color-muted)]">{item.label}</span><span className="min-w-0 flex-1 truncate text-right font-medium">{item.value}</span>
        <ChevronRight className="h-3.5 w-3.5 text-[var(--color-muted)]" />
      </Link> : <div className="flex items-start justify-between gap-3 px-4 py-3 text-[12px]">
        <span className="text-[var(--color-muted)]">{item.label}</span><span className="min-w-0 break-words text-right font-medium">{item.value}</span>
      </div>}
    </li>)}</ul> : <p className="px-4 py-5 text-[12px] text-[var(--color-muted)]">{empty}</p>}
  </section>;
}
