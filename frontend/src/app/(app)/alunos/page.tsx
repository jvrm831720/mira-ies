"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Search, SlidersHorizontal, Users, X } from "lucide-react";
import { Header } from "@/components/layout/header";
import { StudentDrawer } from "@/components/students/student-drawer";
import { RiskBadge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";

function AlunosContent() {
  const searchParams = useSearchParams();
  const [risk, setRisk] = useState(searchParams.get("risk") || "");
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["students", risk],
    queryFn: () => api.students({ risk_level: risk || undefined, limit: 100 }),
  });

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("pt-BR");
    if (!normalized) return data?.students || [];
    return (data?.students || []).filter((student) =>
      [student.nome, student.matricula, student.curso].some((field) =>
        field?.toLocaleLowerCase("pt-BR").includes(normalized)
      )
    );
  }, [data, query]);

  const hasFilters = Boolean(query || risk);

  return (
    <>
      <Header title="Alunos" subtitle="Encontre quem precisa de atenção e abra a ficha." />
      <main className="mx-auto w-full max-w-[1600px] space-y-5 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Base estudantil
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">Lista de alunos</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {isLoading
                ? "Carregando sua base…"
                : `${filtered.length.toLocaleString("pt-BR")} ${
                    filtered.length === 1 ? "aluno encontrado" : "alunos encontrados"
                  }`}
            </p>
          </div>
          <Link
            href="/importar"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90"
          >
            <Users className="h-4 w-4" /> Importar ou atualizar base{" "}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <Card className="overflow-visible">
          <CardContent className="p-4 md:p-5">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px_auto]">
              <label className="relative block">
                <span className="sr-only">Buscar</span>
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Buscar nome, matrícula ou curso"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="pl-10"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    aria-label="Limpar busca"
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:bg-muted"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </label>
              <label className="relative block">
                <span className="sr-only">Risco</span>
                <SlidersHorizontal className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <select
                  value={risk}
                  onChange={(e) => setRisk(e.target.value)}
                  className="h-11 w-full appearance-none rounded-xl border border-input bg-white pl-10 pr-3 text-sm outline-none focus:ring-2 focus:ring-primary/25"
                >
                  <option value="">Todos os níveis</option>
                  <option value="critico">Risco crítico</option>
                  <option value="medio">Risco médio</option>
                  <option value="baixo">Risco baixo</option>
                </select>
              </label>
              <div className="flex items-center justify-end">
                {hasFilters && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery("");
                      setRisk("");
                    }}
                    className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-muted-foreground hover:bg-muted"
                  >
                    <X className="h-3.5 w-3.5" /> Limpar filtros
                  </button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <div className="hidden grid-cols-[minmax(220px,1.4fr)_minmax(160px,1fr)_140px_100px] gap-3 border-b border-border bg-muted/50 px-5 py-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground md:grid">
            <span>Aluno</span>
            <span>Curso</span>
            <span>Nível de risco</span>
            <span className="text-right">Score</span>
          </div>

          {isLoading && (
            <div className="space-y-3 p-5">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-[62px] w-full rounded-xl" />
              ))}
            </div>
          )}

          {!isLoading && isError && (
            <div role="alert" className="m-5 rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-900">
              <p className="font-semibold">Não foi possível carregar a lista.</p>
              <button type="button" onClick={() => void refetch()} className="mt-2 font-medium underline">
                Tentar novamente
              </button>
            </div>
          )}

          {!isLoading && !isError && filtered.length === 0 && (
            <div className="flex flex-col items-center px-5 py-14 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-secondary text-primary">
                <Search className="h-5 w-5" />
              </span>
              <h3 className="mt-4 text-sm font-semibold">
                {hasFilters ? "Nenhum resultado com esses filtros" : "Sua lista começa com uma importação"}
              </h3>
              <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                {hasFilters
                  ? "Ajuste a busca ou remova um filtro."
                  : "Adicione sua base para visualizar riscos."}
              </p>
            </div>
          )}

          {!isLoading && !isError && filtered.length > 0 && (
            <div className="divide-y divide-border/80">
              {filtered.map((student) => (
                <button
                  key={student.id}
                  type="button"
                  onClick={() => setSelectedId(student.id)}
                  className="grid w-full gap-2 px-4 py-4 text-left transition hover:bg-secondary/45 sm:px-5 md:grid-cols-[minmax(220px,1.4fr)_minmax(160px,1fr)_140px_100px] md:items-center md:gap-3"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">
                      {student.nome || "Sem nome"}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      Matrícula {student.matricula || "—"}
                    </span>
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {student.curso || "Curso não informado"}
                  </span>
                  <span>
                    <RiskBadge level={student.risk_level} />
                  </span>
                  <span className="text-left text-sm font-semibold tabular-nums md:text-right">
                    {formatScore(student.risk_score)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </main>

      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

export default function AlunosPage() {
  return (
    <Suspense
      fallback={
        <main className="p-8">
          <Skeleton className="mb-4 h-8 w-48" />
          <Skeleton className="h-64 w-full rounded-2xl" />
        </main>
      }
    >
      <AlunosContent />
    </Suspense>
  );
}
