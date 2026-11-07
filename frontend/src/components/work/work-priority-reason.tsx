import type { WorkActivity } from "@/types/work";

/** Explanations are supplied by the server; never fabricate a priority/risk score. */
export function WorkPriorityReason({ activity }: { activity: WorkActivity }) {
  const reasons = activity.priority_reasons || [];
  return <section aria-label="Motivos da prioridade" className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
    <p className="text-xs font-semibold text-[var(--color-ink)]">Por que está nesta posição?</p>
    {reasons.length ? <ul className="mt-2 space-y-1.5">
      {reasons.map((reason, index) => <li key={reason.code + index} className="flex gap-2 text-xs text-[var(--color-slate-600)]">
        <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-blue)]" />
        <span>{reason.label}</span>
      </li>)}
    </ul> : <p className="mt-2 text-xs text-[var(--color-muted)]">
      Justificativa não disponibilizada. Atualize a fila para consultar os motivos registrados.
    </p>}
    <p className="mt-2 text-[length:var(--type-caption)] text-[var(--color-muted)]">
      Priorização operacional por prazo e prioridade atribuída; não é score de evasão, chance de pagamento ou sucesso de envio.
    </p>
  </section>;
}
