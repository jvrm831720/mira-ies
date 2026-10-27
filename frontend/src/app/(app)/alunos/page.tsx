"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Search,
  SlidersHorizontal,
  Users,
  X,
  ChevronRight,
  Upload,
  AlertTriangle,
  CircleHelp,
  Activity,
  RefreshCw,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { StudentDrawer } from "@/components/students/student-drawer";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn, formatScore } from "@/lib/utils";

type StudentTab = "todos" | "risco" | "sem_classificacao" | "acompanhamento";
type StudentSort = "risk_desc" | "risk_asc" | "name_asc";

function initials(name?: string | null) {
  if (!name?.trim()) return "—";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toLocaleUpperCase("pt-BR");
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function followUpLabel(status?: string) {
  if (!status) return "Sem registro";
  const normalized = status.toLowerCase();
  if (["planned", "pending", "queued"].includes(normalized)) return "Aguardando ação";
  if (["sent", "delivered", "read", "replied", "in_progress"].includes(normalized))
    return "Em acompanhamento";
  if (["failed", "error", "skipped"].includes(normalized)) return "Requer revisão";
  if (["completed", "done", "resolved"].includes(normalized)) return "Concluído";
  return status.replaceAll("_", " ");
}

function businessSignalText(raw?: string | null): string | null {
  if (!raw?.trim()) return null;
  const t = raw.trim();
  if (/\/api\/|GET\s+\/|POST\s+\/|SHAP sob demanda|students\/\{?id\}?\/risk/i.test(t)) {
    return null;
  }
  return t;
}

function primarySignal(student: {
  risk_level?: string | null;
  risk_score?: number | null;
  shap_summary?: string | null;
  shap_top_factors?: {
    summary?: string;
    top_3?: Array<{ feature?: string; label?: string }>;
    recommended_actions?: string[];
  } | null;
}): { signal: string | null; action: string | null; empty: string } {
  if (!student.risk_level || student.risk_score == null) {
    return {
      signal: null,
      action: null,
      empty: "Ainda não há evidências calculadas",
    };
  }
  const fromSummary = businessSignalText(student.shap_summary);
  const fromFactors = student.shap_top_factors?.top_3
    ?.map((f) => businessSignalText(f.label) || businessSignalText(f.feature))
    .filter(Boolean)
    .join(" · ");
  const signal = fromSummary || fromFactors || null;
  const actionRaw = student.shap_top_factors?.recommended_actions?.[0];
  const action = businessSignalText(actionRaw);
  return {
    signal,
    action,
    empty: "Explicação detalhada indisponível",
  };
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

  const students = useMemo(
    () => studentsQuery.data?.students ?? [],
    [studentsQuery.data?.students]
  );
  const courses = useMemo(
    () =>
      [
        ...new Set(
          students
            .map((student) => student.curso?.trim())
            .filter((value): value is string => Boolean(value))
        ),
      ].sort((a, b) => a.localeCompare(b, "pt-BR")),
    [students]
  );
  const latestLogs = useMemo(() => {
    const map = new Map<string, { status: string; created_at?: string | null }>();
    for (const log of [...(logsQuery.data?.logs || [])].sort(
      (a, b) =>
        (b.created_at ? new Date(b.created_at).getTime() : 0) -
        (a.created_at ? new Date(a.created_at).getTime() : 0)
    )) {
      if (log.student_id && !map.has(log.student_id)) {
        map.set(log.student_id, { status: log.status, created_at: log.created_at });
      }
    }
    return map;
  }, [logsQuery.data]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("pt-BR");
    const result = students.filter((student) => {
      const matchesSearch =
        !normalized ||
        [student.nome, student.matricula, student.curso].some((field) =>
          field?.toLocaleLowerCase("pt-BR").includes(normalized)
        );
      const matchesRisk = !risk || student.risk_level === risk;
      const matchesCourse = !course || student.curso === course;
      const matchesTab =
        tab === "todos" ||
        (tab === "risco" && ["critico", "medio"].includes(student.risk_level || "")) ||
        (tab === "sem_classificacao" &&
          (!student.risk_level || student.risk_score == null)) ||
        (tab === "acompanhamento" && latestLogs.has(student.id));
      return matchesSearch && matchesRisk && matchesCourse && matchesTab;
    });

    return result.sort((a, b) => {
      if (sort === "name_asc") {
        return (a.nome || "").localeCompare(b.nome || "", "pt-BR");
      }
      const scoreA = a.risk_score;
      const scoreB = b.risk_score;
      if (scoreA == null && scoreB == null) {
        return (a.nome || "").localeCompare(b.nome || "", "pt-BR");
      }
      if (scoreA == null) return 1;
      if (scoreB == null) return -1;
      return sort === "risk_desc" ? scoreB - scoreA : scoreA - scoreB;
    });
  }, [students, query, risk, course, tab, latestLogs, sort]);

  const summary = riskSummary.data?.summary;
  const highRisk = summary
    ? summary.critico + summary.medio
    : students.filter((s) => ["critico", "medio"].includes(s.risk_level || "")).length;
  const unclassified =
    summary?.sem_score ??
    students.filter((s) => !s.risk_level || s.risk_score == null).length;
  const hasFilters = Boolean(query || risk || course || tab !== "todos");

  function clearFilters() {
    setQuery("");
    setRisk("");
    setCourse("");
    setSort("risk_desc");
    setTab("todos");
  }

  const isRefreshing =
    studentsQuery.isFetching || riskSummary.isFetching || logsQuery.isFetching;

  return (
    <>
      <Header title="Alunos" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-3 border-b border-[#E5E7EB] pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-[22px] font-semibold tracking-[-0.03em] text-[#111827] sm:text-[24px]">
              Alunos
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">
              Consulte a base, priorize por risco e abra a ficha de quem precisa de atenção.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => {
                void studentsQuery.refetch();
                void riskSummary.refetch();
                void logsQuery.refetch();
              }}
              disabled={isRefreshing}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#111827] transition hover:bg-[#F8FAFC] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
              Atualizar
            </button>
            <Link
              href="/importar"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-4 text-[13px] font-semibold text-white transition hover:bg-[#1D4ED8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              <Upload className="h-3.5 w-3.5" />
              Importar
            </Link>
          </div>
        </section>

        <section aria-label="Indicadores da base" className="grid gap-3 sm:grid-cols-3">
          <MetricCard
            label="Alunos na base"
            value={
              studentsQuery.isLoading
                ? "—"
                : (
                    riskSummary.data?.total_students ??
                    studentsQuery.data?.students.length ??
                    0
                  ).toLocaleString("pt-BR")
            }
            hint="Até 200 registros carregados nesta consulta"
            icon={<Users className="h-4 w-4" />}
            tone="neutral"
          />
          <MetricCard
            label="Risco elevado"
            value={
              studentsQuery.isLoading || riskSummary.isLoading
                ? "—"
                : highRisk.toLocaleString("pt-BR")
            }
            hint="Crítico ou moderado"
            icon={<AlertTriangle className="h-4 w-4" />}
            tone="coral"
          />
          <MetricCard
            label="Sem classificação"
            value={
              studentsQuery.isLoading || riskSummary.isLoading
                ? "—"
                : unclassified.toLocaleString("pt-BR")
            }
            hint="Sem score disponível (não é baixo risco)"
            icon={<CircleHelp className="h-4 w-4" />}
            tone="blue"
          />
        </section>

        <section className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white">
          <div className="border-b border-[#E5E7EB] p-4 sm:p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <label className="relative block min-w-0 flex-1">
                <span className="sr-only">Buscar por nome, matrícula ou curso</span>
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#98A2B3]" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Buscar por nome, matrícula ou curso"
                  className="h-10 w-full rounded-lg border border-[#E5E7EB] bg-white pl-10 pr-9 text-[13px] text-[#111827] outline-none placeholder:text-[#98A2B3] focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => setQuery("")} 
                    aria-label="Limpar busca"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-[#98A2B3] hover:bg-[#F8FAFC] hover:text-[#111827]"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </label>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:w-auto lg:min-w-[420px]">
                <label className="relative block">
                  <span className="sr-only">Filtrar por risco</span>
                  <SlidersHorizontal className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#98A2B3]" />
                  <select
                    value={risk}
                    onChange={(e) => setRisk(e.target.value)}
                    className="h-10 w-full appearance-none rounded-lg border border-[#E5E7EB] bg-white pl-9 pr-3 text-[13px] text-[#344054] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"
                  >
                    <option value="">Todas as classificações</option>
                    <option value="critico">Crítico</option>
                    <option value="medio">Moderado</option>
                    <option value="baixo">Baixo</option>
                  </select>
                </label>
                <label className="block">
                  <span className="sr-only">Filtrar por curso</span>
                  <select
                    value={course}
                    onChange={(e) => setCourse(e.target.value)}
                    className="h-10 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 text-[13px] text-[#344054] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"
                  >
                    <option value="">Todos os cursos</option>
                    {courses.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="sr-only">Ordenar alunos</span>
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value as StudentSort)}
                    className="h-10 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 text-[13px] text-[#344054] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"
                  >
                    <option value="risk_desc">Maior score primeiro</option>
                    <option value="risk_asc">Menor score primeiro</option>
                    <option value="name_asc">Nome (A–Z)</option>
                  </select>
                </label>
              </div>
            </div>

            <div
              className="mt-4 flex flex-wrap items-center gap-2"
              role="tablist"
              aria-label="Segmentos de alunos"
            >
              {(
                [
                  ["todos", "Todos"],
                  ["risco", "Risco elevado"],
                  ["sem_classificacao", "Sem classificação"],
                  ["acompanhamento", "Com acompanhamento"],
                ] as [StudentTab, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={tab === value}
                  onClick={() => setTab(value)}
                  className={cn(
                    "rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]",
                    tab === value
                      ? "bg-[#2563EB] text-white"
                      : "bg-[#F8FAFC] text-[#667085] hover:bg-[#EFF6FF] hover:text-[#2563EB]"
                  )}
                >
                  {label}
                </button>
              ))}
              {hasFilters && (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-[#667085] hover:text-[#111827]"
                >
                  <X className="h-3.5 w-3.5" />
                  Limpar filtros
                </button>
              )}
            </div>
          </div>

          {studentsQuery.isLoading && (
            <div className="space-y-3 p-5">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-[66px] w-full rounded-xl" />
              ))}
            </div>
          )}

          {studentsQuery.isError && (
            <div
              role="alert"
              className="m-4 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5"
            >
              <p className="text-sm font-semibold text-[#B42318]">
                Não foi possível carregar os alunos.
              </p>
              <p className="mt-1 text-sm text-[#667085]">
                Verifique sua conexão e tente novamente.
              </p>
              <button
                type="button"
                onClick={() => void studentsQuery.refetch()}
                className="mt-3 text-sm font-semibold text-[#B42318] underline underline-offset-4"
              >
                Tentar novamente
              </button>
            </div>
          )}

          {!studentsQuery.isLoading && !studentsQuery.isError && (
            <>
              <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5">
                <p className="text-[13px] font-semibold text-[#111827]">
                  Resultados
                  <span className="ml-1 font-normal text-[#98A2B3]">
                    ({filtered.length.toLocaleString("pt-BR")})
                  </span>
                </p>
                {logsQuery.isError && (
                  <span className="text-[11px] text-[#98A2B3]">
                    Acompanhamento indisponível
                  </span>
                )}
              </div>

              {filtered.length === 0 ? (
                <div className="flex flex-col items-center px-5 py-14 text-center">
                  <span className="grid h-12 w-12 place-items-center rounded-xl bg-[#F8FAFC] text-[#667085]">
                    {hasFilters ? (
                      <Search className="h-5 w-5" />
                    ) : (
                      <Users className="h-5 w-5" />
                    )}
                  </span>
                  <h3 className="mt-4 text-[14px] font-semibold text-[#111827]">
                    {hasFilters ? "Nenhum aluno encontrado" : "Sua base começa aqui"}
                  </h3>
                  <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-[#667085]">
                    {hasFilters
                      ? "Tente ajustar os filtros ou remover alguns critérios."
                      : "Importe a base da instituição para consultar os estudantes."}
                  </p>
                  {hasFilters ? (
                    <button
                      type="button"
                      onClick={clearFilters}
                      className="mt-4 text-[13px] font-semibold text-[#2563EB] hover:text-[#1D4ED8]"
                    >
                      Limpar filtros
                    </button>
                  ) : (
                    <Link
                      href="/importar"
                      className="mt-4 inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-4 text-[13px] font-semibold text-white hover:bg-[#1D4ED8]"
                    >
                      Importar alunos
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  )}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[920px] text-left">
                    <thead className="bg-[#F8FAFC] text-[11px] font-semibold uppercase tracking-[0.04em] text-[#667085]">
                      <tr>
                        <th className="px-5 py-3">Aluno</th>
                        <th className="px-4 py-3">Curso</th>
                        <th className="px-4 py-3">Risco</th>
                        <th className="px-4 py-3">Principal sinal</th>
                        <th className="px-4 py-3">Acompanhamento</th>
                        <th className="px-4 py-3">Atualização</th>
                        <th className="px-4 py-3">
                          <span className="sr-only">Abrir</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E5E7EB]">
                      {filtered.map((student) => {
                        const latest = latestLogs.get(student.id);
                        const { signal, action, empty } = primarySignal(student);
                        return (
                          <tr
                            key={student.id}
                            className="group transition hover:bg-[#F8FAFC]"
                          >
                            <td className="px-5 py-3.5">
                              <button
                                type="button"
                                onClick={() => setSelectedId(student.id)}
                                className="flex min-w-0 items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                              >
                                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[11px] font-semibold text-[#2563EB]">
                                  {initials(student.nome)}
                                </span>
                                <span className="min-w-0">
                                  <span className="block max-w-[220px] truncate text-[13px] font-semibold text-[#111827]">
                                    {student.nome || "Nome não informado"}
                                  </span>
                                  <span className="mt-0.5 block text-[11px] text-[#667085]">
                                    {student.matricula || "Identificador não informado"}
                                  </span>
                                </span>
                              </button>
                            </td>
                            <td className="px-4 py-3.5 text-[13px] text-[#344054]">
                              {student.curso || "Não informado"}
                            </td>
                            <td className="px-4 py-3.5">
                              <div className="flex flex-col items-start gap-1">
                                <RiskBadge level={student.risk_level} />
                                <span className="text-[11px] tabular-nums text-[#667085]">
                                  {student.risk_score == null
                                    ? "Sem score"
                                    : formatScore(student.risk_score)}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3.5">
                              <div className="max-w-[260px]">
                                {signal ? (
                                  <p className="text-[12px] leading-relaxed text-[#344054]">
                                    {signal}
                                  </p>
                                ) : (
                                  <p className="text-[12px] text-[#98A2B3]">{empty}</p>
                                )}
                                {action && (
                                  <p className="mt-1 text-[11px] leading-relaxed text-[#667085]">
                                    Sugestão operacional: {action}
                                  </p>
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-3.5">
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
                                  latest
                                    ? "bg-[#EFF6FF] text-[#1D4ED8]"
                                    : "bg-[#F8FAFC] text-[#667085]"
                                )}
                              >
                                <Activity className="h-3 w-3" />
                                {followUpLabel(latest?.status)}
                              </span>
                            </td>
                            <td className="px-4 py-3.5 text-[12px] text-[#667085]">
                              {formatDate(latest?.created_at)}
                            </td>
                            <td className="px-4 py-3.5">
                              <button
                                type="button"
                                onClick={() => setSelectedId(student.id)}
                                aria-label={`Abrir ficha de ${student.nome || "aluno"}`}
                                className="grid h-8 w-8 place-items-center rounded-lg text-[#98A2B3] transition hover:bg-white hover:text-[#2563EB] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                              >
                                <ChevronRight className="h-4 w-4" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex items-center justify-between border-t border-[#E5E7EB] bg-[#F8FAFC] px-4 py-3 text-[11px] text-[#667085] sm:px-5">
                <span>
                  Mostrando {filtered.length.toLocaleString("pt-BR")} de{" "}
                  {students.length.toLocaleString("pt-BR")} alunos carregados (limite 200)
                </span>
                <span className="hidden sm:inline">
                  Sem score não é tratado como baixo risco
                </span>
              </div>
            </>
          )}
        </section>

        {logsQuery.isError && (
          <p className="text-[12px] text-[#98A2B3]">
            Não foi possível consultar o histórico de acompanhamento; os estados dessa
            coluna podem estar incompletos.
          </p>
        )}
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

function MetricCard({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone: "neutral" | "coral" | "blue";
}) {
  const tones = {
    neutral: "text-[#667085]",
    coral: "text-[#B42318]",
    blue: "text-[#2563EB]",
  };
  return (
    <article className="rounded-xl border border-[#E5E7EB] bg-white p-4 transition hover:border-[#D0D5DD] hover:shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#98A2B3]">
          {label}
        </p>
        <span className={cn("shrink-0", tones[tone])}>{icon}</span>
      </div>
      <p className="mt-4 text-[28px] font-semibold leading-none tracking-[-0.04em] tabular-nums text-[#111827]">
        {value}
      </p>
      <p className="mt-2 text-[11px] leading-snug text-[#667085]">{hint}</p>
    </article>
  );
}

export default function AlunosPage() {
  return (
    <Suspense
      fallback={
        <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 py-10">
          <Skeleton className="h-8 w-48" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </div>
          <Skeleton className="h-64 rounded-xl" />
        </main>
      }
    >
      <AlunosContent />
    </Suspense>
  );
}
