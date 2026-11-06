import { RiskBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatScore, cn } from "@/lib/utils";
import { copy } from "@/lib/copy";
import type { StudentRisk } from "@/types/api";
import { ChevronRight } from "@/components/ui/icons";
import Link from "next/link";
import { businessSignalText } from "@/components/students/students-list-helpers";

export function CriticalList({
  students,
  loading,
  onSelect,
  showExplanations = false,
}: {
  students?: StudentRisk[];
  loading?: boolean;
  onSelect?: (id: string) => void;
  showExplanations?: boolean;
}) {
  return (
    <Card className="border-[var(--color-border)] shadow-none">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 border-b border-[var(--color-border)] pb-4">
        <div>
          <CardTitle className="text-[15px] tracking-[-0.02em] text-[var(--color-ink)]">
            {copy.criticalNow}
          </CardTitle>
          <CardDescription className="mt-1 text-[12px] text-[var(--color-slate-600)]">
            Comece por quem combina maior risco e maior urgência.
          </CardDescription>
        </div>
        <Link
          href="/alunos?risk=critico"
          className={cn(
            "inline-flex h-9 items-center rounded-lg bg-[var(--color-blue)] px-3 text-xs font-semibold text-white transition hover:bg-[var(--color-blue)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"
          )}
        >
          Ver todos
        </Link>
      </CardHeader>
      <CardContent className="space-y-2 pt-4">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}

        {!loading && (!students || students.length === 0) && (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-10 text-center">
            <p className="text-sm font-semibold text-[var(--color-ink)]">{copy.emptyStudents}</p>
            <p className="mt-1 text-xs text-[var(--color-slate-600)]">
              Quando houver alunos prioritários, eles serão listados aqui.
            </p>
          </div>
        )}

        {!loading &&
          students?.slice(0, 8).map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onSelect?.(s.id)}
              className="group flex w-full items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] px-3.5 py-3 text-left transition hover:border-[var(--color-border)] hover:bg-white sm:gap-4 sm:px-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-[13px] font-semibold text-[var(--color-ink)]">
                    {s.nome || "Sem nome"}
                  </p>
                  <RiskBadge level={s.risk_level} />
                </div>
                <p className="mt-0.5 truncate text-xs text-[var(--color-slate-600)]">
                  {s.matricula}
                  {s.curso ? ` · ${s.curso}` : ""}
                </p>
                {showExplanations && s.shap_top_factors?.top_3?.length ? <div className="mt-2 flex flex-wrap gap-1" aria-label="Principais fatores explicativos">
                  {s.shap_top_factors.top_3.slice(0, 3).map((factor, index) => {
                    const label = businessSignalText(factor.label) || businessSignalText(factor.feature);
                    return label ? <span key={index} className="rounded-[var(--radius-md)] border border-[var(--color-peach-tint-border)] bg-[var(--color-peach-tint)] px-1.5 py-0.5 text-[11px] text-[var(--color-ink)]">{label}</span> : null;
                  })}
                </div> : null}
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold tracking-[-0.04em] tabular-nums text-[var(--color-ink)]">
                  {formatScore(s.risk_score)}
                </p>
                <p className="text-[11px] text-[var(--color-muted)]">score</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-[var(--color-border)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-blue)]" />
            </button>
          ))}
      </CardContent>
    </Card>
  );
}
