"use client";
import { useQuery } from "@tanstack/react-query";
import { TrendingDown, TrendingUp } from "@/components/ui/icons";
import { api } from "@/lib/api";
import type { RiskHistoryAssessment, RiskMovement } from "@/types/api";

/** A delta is meaningful only if both scoring contracts match. */
export function comparableRiskDelta(recent?: RiskHistoryAssessment, previous?: RiskHistoryAssessment): number | null {
  if (!recent || !previous || recent.score_semantics_version !== previous.score_semantics_version ||
      recent.model_scope !== previous.model_scope || (recent.model_version || "") !== (previous.model_version || "")) return null;
  return recent.score - previous.score;
}

export function RiskScoreTrend({ score, movement }: { score?: number | null; movement?: RiskMovement }) {
  if (typeof score !== "number" || !Number.isFinite(score)) return <span title="Score não calculado">—</span>;
  const delta = movement && Math.abs(movement.current_score - score) < 0.01 && !["mudanca_modelo", "sem_historico_comparavel"].includes(movement.change_type)
    ? movement.delta : null;
  return <span className="inline-flex items-center gap-2 font-mono text-xs tabular-nums">
    <span>{Math.round(score)}</span>
    {typeof delta === "number" && Number.isFinite(delta) && delta !== 0 &&
      <span title={`Variação comparável no período: ${delta > 0 ? "+" : ""}${delta.toLocaleString("pt-BR")} pontos`}
        className={delta > 0 ? "inline-flex items-center gap-0.5 text-[length:var(--type-caption)] text-[var(--color-red)]" : "inline-flex items-center gap-0.5 text-[length:var(--type-caption)] text-[var(--color-green)]"}>
        {delta > 0 ? <TrendingUp className="h-3 w-3" aria-hidden="true" /> : <TrendingDown className="h-3 w-3" aria-hidden="true" />}
        {delta > 0 ? "+" : ""}{Math.round(delta)}
      </span>}
  </span>;
}

export function StudentRiskTrend({ studentId }: { studentId: string }) {
  const history = useQuery({
    queryKey: ["student-risk-history", studentId],
    queryFn: () => api.studentRiskHistory(studentId, { page: 1, page_size: 12 }),
    retry: false,
    enabled: Boolean(studentId),
    staleTime: 45_000,
  });
  if (history.isLoading) return <span role="status" className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Consultando histórico…</span>;
  if (history.isError) return <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Tendência indisponível</span>;
  const ordered = [...(history.data?.assessments || [])].sort((a,b) =>
    new Date(b.evaluated_at).getTime() - new Date(a.evaluated_at).getTime());
  const delta = comparableRiskDelta(ordered[0], ordered[1]);
  if (delta === null) return <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Sem avaliações comparáveis</span>;
  if (delta === 0) return <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Estável vs. avaliação anterior</span>;
  return <span className={delta > 0 ? "inline-flex items-center gap-1 text-[length:var(--type-caption)] text-[var(--color-red)]" : "inline-flex items-center gap-1 text-[length:var(--type-caption)] text-[var(--color-green)]"}>
    {delta > 0 ? <TrendingUp className="h-3.5 w-3.5" aria-hidden="true"/> : <TrendingDown className="h-3.5 w-3.5" aria-hidden="true"/>}
    {delta > 0 ? "+" : ""}{Math.round(delta)} pontos vs. avaliação anterior
  </span>;
}
