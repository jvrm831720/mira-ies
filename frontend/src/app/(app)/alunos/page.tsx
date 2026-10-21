"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";

function AlunosContent() {
  const searchParams = useSearchParams();
  const initialRisk = searchParams.get("risk") || "";
  const [risk, setRisk] = useState(initialRisk);
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["students", risk],
    queryFn: () => api.students({ risk_level: risk || undefined, limit: 100 }),
  });

  const filtered = useMemo(() => {
    const list = data?.students || [];
    if (!q.trim()) return list;
    const s = q.toLowerCase();
    return list.filter(
      (st) =>
        st.nome?.toLowerCase().includes(s) ||
        st.matricula?.toLowerCase().includes(s) ||
        st.curso?.toLowerCase().includes(s)
    );
  }, [data, q]);

  return (
    <>
      <Header title="Alunos" subtitle="Busque, filtre e abra a ficha de risco" />
      <main className="space-y-4 p-4 md:p-8">
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            placeholder="Buscar nome, matrícula ou curso..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="sm:max-w-sm"
          />
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={risk}
            onChange={(e) => setRisk(e.target.value)}
          >
            <option value="">Todos os níveis</option>
            <option value="critico">Crítico</option>
            <option value="medio">Médio</option>
            <option value="baixo">Baixo</option>
          </select>
        </div>

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Aluno</th>
                    <th className="px-4 py-3 font-medium">Curso</th>
                    <th className="px-4 py-3 font-medium">Nível</th>
                    <th className="px-4 py-3 font-medium text-right">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading &&
                    Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="border-b border-border">
                        <td className="px-4 py-3" colSpan={4}>
                          <Skeleton className="h-6 w-full" />
                        </td>
                      </tr>
                    ))}
                  {!isLoading && filtered.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-10 text-center text-muted-foreground">
                        Nenhum aluno encontrado com esses filtros.
                      </td>
                    </tr>
                  )}
                  {!isLoading &&
                    filtered.map((s) => (
                      <tr key={s.id} className="border-b border-border/70 hover:bg-muted/30">
                        <td className="px-4 py-3">
                          <Link href={`/alunos/${s.id}`} className="font-medium hover:text-primary">
                            {s.nome || "Sem nome"}
                          </Link>
                          <p className="text-xs text-muted-foreground">{s.matricula}</p>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{s.curso || "—"}</td>
                        <td className="px-4 py-3">
                          <RiskBadge level={s.risk_level} />
                        </td>
                        <td className="px-4 py-3 text-right font-semibold tabular-nums">
                          {formatScore(s.risk_score)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </main>
    </>
  );
}

export default function AlunosPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8">
          <Skeleton className="mb-4 h-8 w-48" />
          <Skeleton className="h-64 w-full" />
        </div>
      }
    >
      <AlunosContent />
    </Suspense>
  );
}
