"use client";
import Link from "next/link";
import { Activity, ArrowRight } from "@/components/ui/icons";
import type { RiskMovement } from "@/types/api";

type Props = { movements: RiskMovement[]; loading: boolean; unavailable: boolean; truncated: boolean; onOpen: (id: string) => void };
export function RiskMovementsFeed({ movements, loading, unavailable, truncated, onOpen }: Props) {
  const relevant = movements.filter(m => m.change_type === "risco_aumentou" || m.change_type === "risco_diminuiu")
    .sort((a,b) => new Date(b.current_evaluated_at).getTime() - new Date(a.current_evaluated_at).getTime())
    .slice(0, 5);
  return <section aria-label="Movimentações de risco" className="border-b border-[var(--color-border)] px-4 py-3 sm:px-6">
    <div className="mb-2 flex items-center justify-between gap-3">
      <h2 className="flex items-center gap-2 text-[13px] font-semibold text-[var(--color-ink)]"><Activity className="h-4 w-4" aria-hidden="true"/> Movimentações · últimos 30 dias</h2>
      <Link href="/monitoramento" className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-blue)] hover:underline">Monitoramento <ArrowRight className="h-3 w-3" /></Link>
    </div>
    {loading ? <div role="status" className="flex gap-2" aria-label="Carregando movimentações">
      {[1,2,3].map(i => <span key={i} className="h-10 flex-1 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-panel)] motion-reduce:animate-none"/>)}
    </div> : unavailable ? <p role="alert" className="text-[12px] text-[var(--color-muted)]">Movimentações indisponíveis. Consulte Monitoramento.</p>
    : !relevant.length ? <p className="text-[12px] text-[var(--color-muted)]">Nenhuma mudança comparável encontrada no período consultado.</p>
    : <div className="flex gap-2 overflow-x-auto pb-1">
      {relevant.map(item => <button type="button" key={item.student_id} onClick={() => onOpen(item.student_id)}
        className="min-w-[200px] max-w-[280px] flex-1 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-canvas)] px-3 py-2 text-left transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] motion-reduce:transition-none">
        <span className="block truncate text-[12px] font-medium text-[var(--color-ink)]">{item.student_name || item.matricula || "Aluno"}</span>
        <span className={item.change_type === "risco_aumentou" ? "text-[11px] text-[var(--color-red)]" : "text-[11px] text-[var(--color-green)]"}>
          {item.change_type === "risco_aumentou" ? "Risco aumentou" : "Risco diminuiu"}
          {typeof item.delta === "number" ? ` · ${item.delta > 0 ? "+" : ""}${Math.round(item.delta)} pts` : ""}
        </span>
      </button>)}
    </div>}
    {truncated && <p className="mt-2 text-[11px] text-[var(--color-muted)]">A consulta foi limitada; outros alunos podem ter movimentações.</p>}
  </section>;
}
