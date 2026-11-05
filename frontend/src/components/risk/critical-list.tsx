import { RiskBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatScore, cn } from "@/lib/utils";
import { copy } from "@/lib/copy";
import type { StudentRisk } from "@/types/api";
import { ChevronRight } from "@/components/ui/icons";
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
    <Card className="border-[#E5E7EB] shadow-none">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 border-b border-[#E5E7EB] pb-4">
        <div>
          <CardTitle className="text-[15px] tracking-[-0.02em] text-[#111827]">
            {copy.criticalNow}
          </CardTitle>
          <CardDescription className="mt-1 text-[12px] text-[#667085]">
            Comece por quem combina maior risco e maior urgência.
          </CardDescription>
        </div>
        <Link
          href="/alunos?risk=critico"
          className={cn(
            "inline-flex h-9 items-center rounded-lg bg-[#2563EB] px-3 text-xs font-semibold text-white transition hover:bg-[#1D4ED8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
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
          <div className="rounded-xl border border-dashed border-[#E5E7EB] bg-[#F8FAFC] px-4 py-10 text-center">
            <p className="text-sm font-semibold text-[#111827]">{copy.emptyStudents}</p>
            <p className="mt-1 text-xs text-[#667085]">
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
              className="group flex w-full items-center gap-3 rounded-xl border border-[#E5E7EB] bg-[#F8FAFC] px-3.5 py-3 text-left transition hover:border-[#CBD5E1] hover:bg-white sm:gap-4 sm:px-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-[13px] font-semibold text-[#111827]">
                    {s.nome || "Sem nome"}
                  </p>
                  <RiskBadge level={s.risk_level} />
                </div>
                <p className="mt-0.5 truncate text-xs text-[#667085]">
                  {s.matricula}
                  {s.curso ? ` · ${s.curso}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold tracking-[-0.04em] tabular-nums text-[#111827]">
                  {formatScore(s.risk_score)}
                </p>
                <p className="text-[11px] text-[#98A2B3]">score</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-[#D0D5DD] transition group-hover:translate-x-0.5 group-hover:text-[#2563EB]" />
            </button>
          ))}
      </CardContent>
    </Card>
  );
}
