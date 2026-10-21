import Link from "next/link";
import { RiskBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatScore, cn } from "@/lib/utils";
import { copy } from "@/lib/copy";
import type { StudentRisk } from "@/types/api";
import { ChevronRight } from "lucide-react";

export function CriticalList({
  students,
  loading,
}: {
  students?: StudentRisk[];
  loading?: boolean;
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
            "inline-flex h-8 items-center rounded-md border border-border px-3 text-xs font-medium hover:bg-muted"
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
          <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
            {copy.emptyStudents}
          </div>
        )}

        {!loading &&
          students?.slice(0, 8).map((s) => (
            <Link
              key={s.id}
              href={`/alunos/${s.id}`}
              className="flex items-center gap-4 rounded-lg border border-border/80 px-4 py-3 transition hover:bg-muted/50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-medium text-foreground">{s.nome || "Sem nome"}</p>
                  <RiskBadge level={s.risk_level} />
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {s.matricula}
                  {s.curso ? ` · ${s.curso}` : ""}
                  {s.shap_summary ? ` · ${s.shap_summary}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold tabular-nums">{formatScore(s.risk_score)}</p>
                <p className="text-[11px] text-muted-foreground">score</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
          ))}
      </CardContent>
    </Card>
  );
}
