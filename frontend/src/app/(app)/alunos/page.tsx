"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Search, SlidersHorizontal, Users, X, ChevronRight, Upload, AlertTriangle, CircleHelp, Activity, RefreshCw } from "lucide-react";
import { Header } from "@/components/layout/header";
import { StudentDrawer } from "@/components/students/student-drawer";
import { RiskBadge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";

type StudentTab = "todos" | "risco" | "sem_classificacao" | "acompanhamento";
type StudentSort = "risk_desc" | "risk_asc" | "name_asc";

function initials(name?: string | null) {
  if (!name?.trim()) return "—";
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toLocaleUpperCase("pt-BR");
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function followUpLabel(status?: string) {
  if (!status) return "Sem registro";
  const normalized = status.toLowerCase();
  if (["planned", "pending", "queued"].includes(normalized)) return "Aguardando ação";
  if (["sent", "delivered", "read", "replied", "in_progress"].includes(normalized)) return "Em acompanhamento";
  if (["failed", "error", "skipped"].includes(normalized)) return "Requer revisão";
  if (["completed", "done", "resolved"].includes(normalized)) return "Concluído";
  return status.replaceAll("_", " ");
}

function AlunosContent() {
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [risk, setRisk] = useState(() => {
    const requestedRisk = searchParams.get("risk") || "";
    return ["critico", "medio", "baixo"].includes(requestedRisk) ? requestedRisk : "";
  });
  const [course, setCourse] = useState("");
  const [sort, setSort] = useState<StudentSort>("risk_desc");
  const [tab, setTab] = useState<StudentTab>("todos");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const studentsQuery = useQuery({
    queryKey: ["students", "explorer"],
    queryFn: () => api.students({ limit: 200 }),
  });
  const riskSummary = useQuery({
    queryKey: ["risk-summary", "students"],
    queryFn: () => api.riskSummary(),
    retry: false,
  });
  const logsQuery = useQuery({
    queryKey: ["retention-logs", "students-follow-up"],
    queryFn: () => api.retentionLogs({ limit: 100 }),
    retry: false,
  });

  const students = useMemo(() => studentsQuery.data?.students ?? [], [studentsQuery.data?.students]);
  const courses = useMemo(
    () => [...new Set(students.map((student) => student.curso?.trim()).filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b, "pt-BR")),
    [students]
  );
  const latestLogs = useMemo(() => {
    const map = new Map<string, { status: string; created_at?: string | null }>();
    for (const log of [...(logsQuery.data?.logs || [])].sort((a, b) => (b.created_at ? new Date(b.created_at).getTime() : 0) - (a.created_at ? new Date(a.created_at).getTime() : 0))) {
      if (log.student_id && !map.has(log.student_id)) map.set(log.student_id, { status: log.status, created_at: log.created_at });
    }
    return map;
  }, [logsQuery.data]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("pt-BR");
    const result = students.filter((student) => {
      const matchesSearch = !normalized || [student.nome, student.matricula, student.curso].some((field) => field?.toLocaleLowerCase("pt-BR").includes(normalized));
      const matchesRisk = !risk || student.risk_level === risk;
      const matchesCourse = !course || student.curso === course;
      const matchesTab =
        tab === "todos" ||
        (tab === "risco" && ["critico", "medio"].includes(student.risk_level || "")) ||
        (tab === "sem_classificacao" && (!student.risk_level || student.risk_score == null)) ||
        (tab === "acompanhamento" && latestLogs.has(student.id));
      return matchesSearch && matchesRisk && matchesCourse && matchesTab;
    });
    return result.sort((a, b) => {
      if (sort === "name_asc") return (a.nome || "").localeCompare(b.nome || "", "pt-BR");
      const scoreA = a.risk_score;
      const scoreB = b.risk_score;
      if (scoreA == null && scoreB == null) return (a.nome || "").localeCompare(b.nome || "", "pt-BR");
      if (scoreA == null) return 1;
      if (scoreB == null) return -1;
      return sort === "risk_desc" ? scoreB - scoreA : scoreA - scoreB;
    });
  }, [students, query, risk, course, tab, latestLogs, sort]);

  const summary = riskSummary.data?.summary;
  const highRisk = summary ? summary.critico + summary.medio : students.filter((student) => ["critico", "medio"].includes(student.risk_level || "")).length;
  const unclassified = summary?.sem_score ?? students.filter((student) => !student.risk_level || student.risk_score == null).length;
  const hasFilters = Boolean(query || risk || course || tab !== "todos");

  function clearFilters() {
    setQuery("");
    setRisk("");
    setCourse("");
    setSort("risk_desc");
    setTab("todos");
  }

  return (
    <>
      <Header title="Alunos" subtitle="Consulte a base e identifique quem precisa de acompanhamento." />
      <main className="mx-auto w-full max-w-[1600px] space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7 mira-page">
        <section className="flex flex-col justify-between gap-4 border-b border-[var(--border-subtle)] pb-5 sm:flex-row sm:items-end">
          <div>
            <p className="mira-eyebrow">Inteligência educacional</p>
            <h2 className="mt-2 text-[24px] font-semibold tracking-[-0.03em] text-[#111827]">Base de alunos</h2>
            <p className="mt-1 text-[13px] text-[#667085]">Explore os estudantes, entenda os sinais de risco e consulte o acompanhamento.</p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => { void studentsQuery.refetch(); void riskSummary.refetch(); void logsQuery.refetch(); }} disabled={studentsQuery.isFetching} className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-3.5 text-sm font-semibold text-neutral-700 shadow-sm transition hover:bg-neutral-50 disabled:opacity-60">
              <RefreshCw className={`h-3.5 w-3.5 ${studentsQuery.isFetching ? "animate-spin" : ""}`} /> Atualizar
            </button>
            <Link href="/importar" className="inline-flex h-10 items-center justify-center gap-2 rounded-[var(--radius-control)] bg-[#2563EB] px-4 text-sm font-semibold text-white transition hover:bg-[#1D4ED8]">
              <Upload className="h-4 w-4" /> Importar alunos
            </Link>
          </div>
        </section>

        <section aria-label="Indicadores da base" className="grid gap-3 sm:grid-cols-3">
          <MetricCard label="Total na base" value={studentsQuery.isLoading ? "—" : (riskSummary.data?.total_students ?? studentsQuery.data?.students.length ?? 0).toLocaleString("pt-BR")} detail="Estudantes retornados pela base" icon={<Users className="h-5 w-5" />} tone="neutral" />
          <MetricCard label="Risco elevado" value={studentsQuery.isLoading || riskSummary.isLoading ? "—" : highRisk.toLocaleString("pt-BR")} detail="Classificados como crítico ou moderado" icon={<AlertTriangle className="h-5 w-5" />} tone="coral" />
          <MetricCard label="Sem classificação" value={studentsQuery.isLoading || riskSummary.isLoading ? "—" : unclassified.toLocaleString("pt-BR")} detail="Sem score de risco disponível" icon={<CircleHelp className="h-5 w-5" />} tone="blue" />
        </section>

        <section className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white shadow-sm">
          <div className="border-b border-[var(--border-subtle)] p-4 sm:p-5">
            <div className="flex flex-col gap-3 xl:flex-row">
              <label className="relative block min-w-0 flex-1">
                <span className="sr-only">Buscar por nome, matrícula ou identificador</span>
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
                <Input placeholder="Buscar por nome, matrícula ou identificador..." value={query} onChange={(event) => setQuery(event.target.value)} className="h-11 rounded-[var(--radius-control)] border-[var(--border-subtle)] bg-white pl-10 pr-10 shadow-none placeholder:text-neutral-400 focus-visible:ring-neutral-900/15" />
                {query && <button type="button" onClick={() => setQuery("")} aria-label="Limpar busca" className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-neutral-400 transition hover:bg-neutral-100 hover:text-neutral-700"><X className="h-3.5 w-3.5" /></button>}
              </label>
              <div className="grid gap-3 sm:grid-cols-2 xl:w-[430px]">
                <label className="relative block">
                  <span className="sr-only">Filtrar por risco</span>
                  <SlidersHorizontal className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
                  <select value={risk} onChange={(event) => setRisk(event.target.value)} className="h-11 w-full appearance-none rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white pl-10 pr-3 text-sm text-neutral-700 outline-none focus:border-neutral-400 focus:ring-2 focus:ring-neutral-900/10">
                    <option value="">Todas as classificações</option><option value="critico">Crítico</option><option value="medio">Moderado</option><option value="baixo">Baixo</option>
                  </select>
                </label>
                {courses.length > 0 && <label className="block"><span className="sr-only">Filtrar por curso</span><select value={course} onChange={(event) => setCourse(event.target.value)} className="h-11 w-full rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-3 text-sm text-neutral-700 outline-none focus:border-neutral-400 focus:ring-2 focus:ring-neutral-900/10"><option value="">Todos os cursos</option>{courses.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}
                <label className="block sm:col-span-2"><span className="sr-only">Ordenar alunos</span><select value={sort} onChange={(event) => setSort(event.target.value as StudentSort)} className="h-10 w-full rounded-[var(--radius-control)] border border-[#E5E7EB] bg-white px-3 text-[13px] text-[#475467] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"><option value="risk_desc">Maior score primeiro</option><option value="risk_asc">Menor score primeiro</option><option value="name_asc">Nome (A–Z)</option></select></label>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2" role="tablist" aria-label="Segmentos de alunos">
              {([
                ["todos", "Todos"],
                ["risco", "Risco elevado"],
                ["sem_classificacao", "Sem classificação"],
                ["acompanhamento", "Com acompanhamento"],
              ] as [StudentTab, string][]).map(([value, label]) => (
                <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => setTab(value)} className={`rounded-full px-3.5 py-2 text-xs font-semibold transition ${tab === value ? "bg-neutral-900 text-white shadow-sm" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"}`}>{label}</button>
              ))}
              {hasFilters && <button type="button" onClick={clearFilters} className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900"><X className="h-3.5 w-3.5" /> Limpar filtros</button>}
            </div>
          </div>

          {studentsQuery.isLoading && <div className="space-y-3 p-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[66px] w-full rounded-xl" />)}</div>}
          {studentsQuery.isError && <div role="alert" className="m-4 rounded-xl border border-red-200 bg-red-50 p-5"><p className="text-sm font-semibold text-red-900">Não foi possível carregar os alunos.</p><p className="mt-1 text-sm text-red-800/80">Verifique sua conexão e tente novamente.</p><button type="button" onClick={() => void studentsQuery.refetch()} className="mt-3 text-sm font-semibold text-red-900 underline underline-offset-4">Tentar novamente</button></div>}

          {!studentsQuery.isLoading && !studentsQuery.isError && <>
            <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5">
              <p className="text-sm font-semibold text-neutral-800">Base de alunos <span className="ml-1 font-normal text-neutral-400">({filtered.length.toLocaleString("pt-BR")})</span></p>
              {logsQuery.isError && <span className="text-xs text-neutral-400">Acompanhamento indisponível</span>}
            </div>
            {filtered.length === 0 ? <div className="flex flex-col items-center px-5 py-14 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-neutral-100 text-neutral-500">{hasFilters ? <Search className="h-5 w-5" /> : <Users className="h-5 w-5" />}</span>
              <h3 className="mt-4 text-sm font-semibold text-neutral-900">{hasFilters ? "Nenhum aluno encontrado" : "Sua base começa aqui"}</h3>
              <p className="mt-1 max-w-sm text-sm leading-relaxed text-neutral-500">{hasFilters ? "Tente ajustar os filtros ou remover alguns critérios." : "Importe a base da instituição para consultar os estudantes."}</p>
              {hasFilters ? <button type="button" onClick={clearFilters} className="mt-4 text-sm font-semibold text-[var(--brand-indigo)] hover:underline">Limpar filtros</button> : <Link href="/importar" className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl bg-neutral-900 px-4 text-sm font-semibold text-white">Importar alunos <ArrowRight className="h-3.5 w-3.5" /></Link>}
            </div> : <div className="overflow-x-auto">
              <table className="w-full min-w-[920px] text-left">
                <thead className="bg-[#F8FAFC] text-[11px] font-semibold text-[#667085]">
                  <tr><th className="px-5 py-3.5">Aluno</th><th className="px-4 py-3.5">Curso</th><th className="px-4 py-3.5">Risco</th><th className="px-4 py-3.5">Principal sinal</th><th className="px-4 py-3.5">Acompanhamento</th><th className="px-4 py-3.5">Atualização</th><th className="px-4 py-3.5"><span className="sr-only">Abrir</span></th></tr>
                </thead>
                <tbody className="divide-y divide-[#EAECF0]">
                  {filtered.map((student) => {
                    const latest = latestLogs.get(student.id);
                    return <tr key={student.id} className="group transition hover:bg-[#F8FAFC]">
                      <td className="px-5 py-4">
                        <button type="button" onClick={() => setSelectedId(student.id)} className="flex min-w-0 items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]">
                          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[11px] font-semibold text-[#2563EB]">{initials(student.nome)}</span>
                          <span className="min-w-0"><span className="block max-w-[240px] truncate text-sm font-semibold text-neutral-900">{student.nome || "Nome não informado"}</span><span className="mt-1 block text-xs text-neutral-500">{student.matricula || "Identificador não informado"}</span></span>
                        </button>
                      </td>
                      <td className="px-4 py-4 text-sm text-neutral-600">{student.curso || "Não informado"}</td>
                      <td className="px-4 py-4"><div className="flex flex-col items-start gap-1.5"><RiskBadge level={student.risk_level} /><span className="text-xs tabular-nums text-neutral-500">{formatScore(student.risk_score)}</span></div></td>
                      <td className="px-4 py-4">
                        {student.risk_level && student.risk_score != null ? (
                          <div className="max-w-[260px]">
                            {student.shap_summary ? <p className="text-xs leading-relaxed text-neutral-700">{student.shap_summary}</p> : student.shap_top_factors?.top_3?.length ? <p className="text-xs leading-relaxed text-neutral-700">{student.shap_top_factors.top_3.map((factor) => factor.label || factor.feature).filter(Boolean).join(" · ")}</p> : <p className="text-xs text-neutral-500">Explicação detalhada indisponível</p>}
                            {student.shap_top_factors?.recommended_actions?.[0] && <p className="mt-1 text-[11px] leading-relaxed text-neutral-400">Próxima ação sugerida: {student.shap_top_factors.recommended_actions[0]}</p>}
                          </div>
                        ) : <span className="text-xs text-neutral-500">Ainda não há evidências calculadas</span>}
                      </td>
                      <td className="px-4 py-4"><span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${latest ? "bg-[#EFF6FF] text-[#1D4ED8]" : "bg-neutral-100 text-neutral-500"}`}><Activity className="h-3 w-3" />{followUpLabel(latest?.status)}</span></td>
                      <td className="px-4 py-4 text-xs text-neutral-500">{formatDate(latest?.created_at)}</td>
                      <td className="px-4 py-4"><button type="button" onClick={() => setSelectedId(student.id)} aria-label={`Abrir ficha de ${student.nome || "aluno"}`} className="grid h-8 w-8 place-items-center rounded-full text-neutral-400 transition hover:bg-white hover:text-neutral-900"><ChevronRight className="h-4 w-4" /></button></td>
                    </tr>;
                  })}
                </tbody>
              </table>
            </div>}
            <div className="flex items-center justify-between border-t border-neutral-100 bg-[#F8FAFC] px-4 py-3 text-xs text-[#667085] sm:px-5"><span>Mostrando {filtered.length.toLocaleString("pt-BR")} de {students.length.toLocaleString("pt-BR")} alunos carregados</span><span className="hidden sm:inline">A classificação e os sinais dependem dos dados disponíveis</span></div>
          </>}
        </section>
        {logsQuery.isError && <p className="text-xs text-neutral-400">Não foi possível consultar o histórico de acompanhamento; os estados dessa coluna podem estar incompletos.</p>}
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

function MetricCard({ label, value, detail, icon, tone }: { label: string; value: string; detail: string; icon: React.ReactNode; tone: "neutral" | "coral" | "blue" }) {
  const tones = { neutral: "bg-[#F2F4F7] text-[#475467]", coral: "bg-[#FEF3F2] text-[#B42318]", blue: "bg-[#EFF6FF] text-[#2563EB]" };
  return <article data-mira-card="true" className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm sm:p-5"><div className="flex items-center justify-between gap-3"><p className="text-[13px] font-medium text-[#667085]">{label}</p><span className={`grid h-9 w-9 place-items-center rounded-lg ${tones[tone]}`}>{icon}</span></div><p className="mt-4 text-[28px] font-semibold leading-none tracking-[-0.04em] tabular-nums text-[#111827]">{value}</p><p className="mt-2 text-xs text-[#667085]">{detail}</p></article>;
}

export default function AlunosPage() {
  return <Suspense fallback={<main className="p-8"><Skeleton className="mb-4 h-8 w-48" /><Skeleton className="h-64 w-full rounded-2xl" /></main>}><AlunosContent /></Suspense>;
}
