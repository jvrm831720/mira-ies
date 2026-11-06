import type { StudentRisk } from "@/types/api";
import { businessSignalText } from "./students-list-helpers";

/** SHAP factors come from the risk API, not invented by the UI. */
export function StudentRiskFactors({ student }: {
  student: Pick<StudentRisk, "risk_score" | "shap_summary" | "shap_top_factors">
}) {
  const factors = student.shap_top_factors?.top_3
    ?.map(f => businessSignalText(f.label) || businessSignalText(f.feature))
    .filter((value): value is string => Boolean(value)).slice(0, 3) || [];
  if (student.risk_score == null) return <p className="text-xs text-[var(--color-muted)]">Sem análise de risco disponível.</p>;
  return <section aria-label="Fatores do risco" className="rounded-[var(--radius-lg)] border border-[var(--color-border)] p-3">
    <h3 className="mb-2 text-xs font-semibold text-[var(--color-ink)]">Fatores que influenciaram a avaliação</h3>
    {factors.length ? <ol className="flex flex-wrap gap-2">
      {factors.map((factor,index) => <li key={index}
        className="rounded-[var(--radius-md)] border border-[var(--color-peach-tint-border)] bg-[var(--color-peach-tint)] px-2 py-1 text-[length:var(--type-caption)] text-[var(--color-ink)]">{factor}</li>)}
    </ol> : <p className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Fatores SHAP não disponibilizados para esta avaliação.</p>}
    {businessSignalText(student.shap_summary) && <p className="mt-2 text-xs text-[var(--color-slate-600)]">{businessSignalText(student.shap_summary)}</p>}
  </section>;
}
