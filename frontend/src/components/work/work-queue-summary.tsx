import { cn } from "@/lib/utils";
import type { workApi } from "@/lib/work-api";

type Summary = Awaited<ReturnType<typeof workApi.summary>>;
type Props = { data?: Summary; isLoading: boolean; isError: boolean };

/** Compact operational inbox scorecard. Metrics are never fabricated. */
export function WorkQueueSummary({ data, isLoading, isError }: Props) {
  const metrics = [
    { label: "Pendentes", value: data?.pending, urgent: false },
    { label: "Atrasadas", value: data?.overdue, urgent: true },
    { label: "Sem responsável", value: data?.unassigned, urgent: true },
    { label: "Urgentes", value: data?.urgent_pending, urgent: true },
    { label: "De campanhas", value: data?.campaign_pending, urgent: false },
    { label: "Concluídas · 7d", value: data?.completed_7d, urgent: false },
  ];
  return <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" aria-label="Resumo da fila">
    {metrics.map(metric => <div key={metric.label} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5">
      <p className="text-[11px] font-medium text-[var(--color-slate-600)]">{metric.label}</p>
      {isLoading ? <div className="mt-2 h-6 w-12 animate-pulse rounded bg-[var(--color-border)] motion-reduce:animate-none" role="status" aria-label="Carregando indicador" />
      : <p className={cn("mt-1 text-[17px] font-semibold tabular-nums", metric.urgent && Number(metric.value) > 0 ? "text-[var(--color-red)]" : "text-[var(--color-ink)]")}>
        {isError || metric.value == null ? "—" : metric.value.toLocaleString("pt-BR")}
      </p>}
    </div>)}
  </div>;
}
