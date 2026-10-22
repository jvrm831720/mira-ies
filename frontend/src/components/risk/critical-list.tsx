import { RiskBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatScore, cn } from "@/lib/utils";
import { copy } from "@/lib/copy";
import type { StudentRisk } from "@/types/api";
import { ChevronRight } from "lucide-react";
import Link from "next/link";

export function CriticalList({
  students,
  loading,
  onSelect,
}: {
  students?: StudentRisk[];
  loading?: boolean;
  onSelect?: (id: string) => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>{copy.criticalNow}</CardTitle>
          <CardDescription>Alunos em risco crítico, ordenados por score</CardDescription>
        </div>
        <Link
          href="/alunos?risk=critico"
          className={cn(
            "inline-flex h-9 items-center rounded-xl border border-border bg-white px-3 text-xs font-semibold transition hover:border-primary/25 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          )}
        >
          Ver todos
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}

        {!loading && (!students || students.length === 0) && (
          <div className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
            <p className="text-sm font-semibold">{copy.emptyStudents}</p>
            <p className="mt-1 text-xs text-muted-foreground">
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
              className="flex w-full items-center gap-3 rounded-xl border border-border/80 bg-white px-3.5 py-3 text-left transition hover:border-primary/20 hover:bg-secondary/35 sm:gap-4 sm:px-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-medium">{s.nome || "Sem nome"}</p>
                  <RiskBadge level={s.risk_level} />
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {s.matricula}
                  {s.curso ? ` · ${s.curso}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold tabular-nums">{formatScore(s.risk_score)}</p>
                <p className="text-[11px] text-muted-foreground">score</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          ))}
      </CardContent>
    </Card>
  );
}
