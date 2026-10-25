"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Search, SlidersHorizontal, Users, X, ChevronRight, Upload } from "lucide-react";
import { Header } from "@/components/layout/header";
import { StudentDrawer } from "@/components/students/student-drawer";
import { RiskBadge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";

function initials(name?: string | null) {
  if (!name?.trim()) return "—";
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toLocaleUpperCase("pt-BR");
}

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
      <main className="mx-auto w-full max-w-[1600px] px-4 pb-10 pt-5 md:px-9 md:pt-7 mira-page">
        <section className="mb-7 flex flex-col justify-between gap-4 border-b border-[var(--border-subtle)] pb-5 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <h2 className="text-2xl font-semibold tracking-[-0.045em] text-neutral-950">Todos os alunos</h2>
            <p className="mt-1 text-sm text-neutral-500">
              {isLoading
                ? "Carregando sua base…"
                : filtered.length.toLocaleString("pt-BR") + (filtered.length === 1 ? " aluno encontrado" : " alunos encontrados")}
            </p>
          </div>
          <Link href="/importar" className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-[var(--radius-pill)] bg-neutral-900 px-4 text-sm font-semibold text-white transition hover:bg-neutral-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-900 focus-visible:ring-offset-2">
            <Upload className="h-4 w-4" /> Importar alunos
          </Link>
        </section>

        <section aria-label="Buscar e filtrar alunos" className="mb-5 flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-3 shadow-sm sm:flex-row sm:p-4">
          <label className="relative block min-w-0 flex-1">
            <span className="sr-only">Buscar aluno</span>
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <Input placeholder="Buscar por nome, matrícula ou curso" value={query} onChange={(e) => setQuery(e.target.value)} className="h-11 rounded-[var(--radius-control)] border-[var(--border-subtle)] bg-[var(--surface-card)] pl-10 pr-10 shadow-none placeholder:text-neutral-400 focus-visible:ring-neutral-900/15" />
            {query && <button type="button" onClick={() => setQuery("")} aria-label="Limpar busca" className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-neutral-400 transition hover:bg-neutral-100 hover:text-neutral-700"><X className="h-3.5 w-3.5" /></button>}
          </label>
          <label className="relative block sm:w-[200px] sm:shrink-0">
            <span className="sr-only">Filtrar por risco</span>
            <SlidersHorizontal className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <select value={risk} onChange={(e) => setRisk(e.target.value)} className="h-11 w-full appearance-none rounded-xl border border-neutral-200 bg-white pl-10 pr-3 text-sm text-neutral-700 outline-none transition focus:border-neutral-400 focus:ring-2 focus:ring-neutral-900/10">
              <option value="">Todos os riscos</option>
              <option value="critico">Risco crítico</option>
              <option value="medio">Risco médio</option>
              <option value="baixo">Risco baixo</option>
            </select>
          </label>
          {hasFilters && <button type="button" onClick={() => { setQuery(""); setRisk(""); }} className="inline-flex h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl px-3 text-sm font-medium text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900"><X className="h-3.5 w-3.5" /> Limpar</button>}
        </section>

        <section aria-label="Lista de alunos" data-mira-card="true" className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white shadow-sm">
          <div className="hidden grid-cols-[minmax(220px,1.5fr)_minmax(150px,1fr)_150px_90px_24px] items-center gap-4 border-b border-[var(--border-subtle)] bg-[var(--surface-page)] px-5 py-4 text-[10px] font-bold uppercase tracking-[0.14em] text-neutral-500 md:grid">
            <span>Aluno</span><span>Curso</span><span>Nível de risco</span><span className="text-right">Score</span><span />
          </div>

          {isLoading && <div className="space-y-3 p-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[66px] w-full rounded-xl" />)}</div>}

          {!isLoading && isError && <div role="alert" className="m-4 rounded-xl border border-red-200 bg-red-50/80 p-5 sm:m-5">
            <p className="text-sm font-semibold text-red-900">Não foi possível carregar os alunos.</p>
            <p className="mt-1 text-sm text-red-800/80">Verifique sua conexão e tente novamente.</p>
            <button type="button" onClick={() => void refetch()} className="mt-3 text-sm font-semibold text-red-900 underline underline-offset-4">Tentar novamente</button>
          </div>}

          {!isLoading && !isError && filtered.length === 0 && <div className="flex flex-col items-center px-5 py-14 text-center sm:py-16">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-neutral-100 text-neutral-500">{hasFilters ? <Search className="h-5 w-5" /> : <Users className="h-5 w-5" />}</span>
            <h3 className="mt-4 text-sm font-semibold text-neutral-900">{hasFilters ? "Nenhum aluno encontrado" : "Sua base começa aqui"}</h3>
            <p className="mt-1 max-w-sm text-sm leading-relaxed text-neutral-500">{hasFilters ? "Tente outro nome ou matrícula, ou remova os filtros." : "Importe a planilha da sua instituição para ver os alunos nesta lista."}</p>
            {hasFilters
              ? <button type="button" onClick={() => { setQuery(""); setRisk(""); }} className="mt-4 text-sm font-semibold text-[var(--brand-indigo)] hover:underline">Limpar busca e filtros</button>
              : <Link href="/importar" className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl bg-neutral-900 px-4 text-sm font-semibold text-white transition hover:bg-neutral-800"><Upload className="h-4 w-4" /> Importar alunos <ArrowRight className="h-3.5 w-3.5" /></Link>}
          </div>}

          {!isLoading && !isError && filtered.length > 0 && <div className="divide-y divide-neutral-100">
            {filtered.map((student) => <button key={student.id} type="button" onClick={() => setSelectedId(student.id)} aria-label={"Abrir ficha de " + (student.nome || "aluno sem nome")}
              className="group grid w-full grid-cols-[minmax(0,1fr)_auto_16px] items-center gap-x-3 gap-y-2 px-4 py-4 text-left transition duration-150 hover:bg-indigo-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-neutral-900/20 sm:px-5 md:grid-cols-[minmax(220px,1.5fr)_minmax(150px,1fr)_150px_90px_24px] md:gap-4 md:py-5">
              <span className="flex min-w-0 items-center gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#f0efff] text-[11px] font-semibold text-[var(--brand-indigo)]">{initials(student.nome)}</span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-neutral-900">{student.nome || "Nome não informado"}</span>
                  <span className="mt-0.5 block truncate text-xs text-neutral-500">Matrícula {student.matricula || "—"}</span>
                  <span className="mt-1 block truncate text-xs text-neutral-500 md:hidden">{student.curso || "Curso não informado"}</span>
                </span>
              </span>
              <span className="hidden truncate text-sm text-neutral-500 md:block">{student.curso || "Não informado"}</span>
              <span className="justify-self-start"><RiskBadge level={student.risk_level} /></span>
              <span className="hidden text-right text-sm font-medium tabular-nums text-neutral-700 md:block">{formatScore(student.risk_score)}</span>
              <ChevronRight className="h-4 w-4 justify-self-end text-neutral-300 transition group-hover:translate-x-0.5 group-hover:text-neutral-500" />
            </button>)}
          </div>}

          {!isLoading && !isError && filtered.length > 0 && <div className="flex items-center justify-between border-t border-neutral-100 bg-neutral-50/50 px-4 py-3 text-xs text-neutral-400 sm:px-5">
            <span>Mostrando {filtered.length.toLocaleString("pt-BR")} {filtered.length === 1 ? "aluno" : "alunos"}</span>
            <span className="hidden sm:inline">Selecione um aluno para ver os detalhes</span>
          </div>}
        </section>
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

export default function AlunosPage() {
  return <Suspense fallback={<main className="p-8"><Skeleton className="mb-4 h-8 w-48" /><Skeleton className="h-64 w-full rounded-2xl" /></main>}><AlunosContent /></Suspense>;
}
