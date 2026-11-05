"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Search,
  Users,
  X,
  ChevronRight,
  Upload,
  RefreshCw,
  Layers,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { StudentDrawer } from "@/components/students/student-drawer";
import {
  KNOWN_GROUP_IDS,
  initials,
  formatDate,
  followUpLabel,
  primarySignal,
  type StudentTab,
  type StudentSort,
} from "@/components/students/students-list-helpers";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn, formatScore } from "@/lib/utils";

export function StudentsListPage() {
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [risk, setRisk] = useState(() => {
    const requestedRisk = searchParams.get("risk") || "";
    return ["critico", "medio", "baixo"].includes(requestedRisk) ? requestedRisk : "";
  });
  const [course, setCourse] = useState("");
  const [sort, setSort] = useState<StudentSort>("risk_desc");
  const [tab, setTab] = useState<StudentTab>(() => {
    const t = searchParams.get("tab") || "";
    if (
      ["todos", "risco", "sem_classificacao", "dados_insuficientes", "acompanhamento"].includes(t)
    ) {
      return t as StudentTab;
    }
    return "todos";
  });
  const [groupId, setGroupId] = useState(() => {
    const g = searchParams.get("group") || "";
    return KNOWN_GROUP_IDS.has(g) ? g : "";
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [visibleLimit, setVisibleLimit] = useState(50);

  const studentsQuery = useQuery({
    queryKey: ["students", "explorer"],
    queryFn: () => api.students({ limit: 500 }),
  });
  const groupsCatalog = useQuery({
    queryKey: ["student-groups", "catalog", "list-filter"],
    queryFn: () => api.studentGroupsCatalog(),
    staleTime: 60_000,
    retry: false,
  });
  const groupMembers = useQuery({
    queryKey: ["student-groups", "members", groupId],
    queryFn: async () => {
      const page = await api.studentGroupMembers(groupId, { limit: 100 });
      const ids = new Set(page.members.map((m) => m.student_id));
      let cursor = page.next_cursor;
      let guard = 0;
      while (cursor && page.has_more !== false && guard < 5) {
        const next = await api.studentGroupMembers(groupId, { limit: 100, cursor });
        next.members.forEach((m) => ids.add(m.student_id));
        cursor = next.next_cursor;
        guard += 1;
        if (!next.has_more) break;
      }
      return ids;
    },
    enabled: Boolean(groupId),
    retry: false,
    staleTime: 30_000,
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

  const memberIds = groupMembers.data;

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
      const matchesGroup = !groupId || (memberIds ? memberIds.has(student.id) : true);
      const matchesTab =
        tab === "todos" ||
        (tab === "risco" && ["critico", "medio"].includes(student.risk_level || "")) ||
        (tab === "sem_classificacao" && (!student.risk_level || student.risk_score == null)) ||
        (tab === "dados_insuficientes" &&
          (!student.risk_level || student.risk_score == null || groupId === "missing_score")) ||
        (tab === "acompanhamento" && latestLogs.has(student.id));
      return matchesSearch && matchesRisk && matchesCourse && matchesTab && matchesGroup;
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
  }, [students, query, risk, course, tab, latestLogs, sort, groupId, memberIds]);

  const visibleStudents = useMemo(
    () => filtered.slice(0, visibleLimit),
    [filtered, visibleLimit]
  );

  const summary = riskSummary.data?.summary;
  const highRisk = summary
    ? summary.critico + summary.medio
    : students.filter((s) => ["critico", "medio"].includes(s.risk_level || "")).length;
  const unclassified =
    summary?.sem_score ?? students.filter((s) => !s.risk_level || s.risk_score == null).length;
  const hasFilters = Boolean(query || risk || course || groupId || tab !== "todos");

  function clearFilters() {
    setQuery("");
    setRisk("");
    setCourse("");
    setSort("risk_desc");
    setTab("todos");
    setGroupId("");
    setVisibleLimit(50);
  }

  function applyGroup(next: string) {
    setGroupId(next);
    setVisibleLimit(50);
    if (next === "missing_score") setTab("dados_insuficientes");
  }

  const isRefreshing =
    studentsQuery.isFetching ||
    riskSummary.isFetching ||
    logsQuery.isFetching ||
    groupMembers.isFetching;

  return (
    <>
      <Header title="Alunos" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-3 border-b border-[#e4e7ec] pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-[22px] font-semibold tracking-[-0.03em] text-[#1c1d1f] sm:text-[24px]">
              Alunos
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#6f7988]">
              Consulte a base, priorize por risco, grupo ou cobertura de dados e abra a ficha.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => {
                void studentsQuery.refetch();
                void riskSummary.refetch();
                void logsQuery.refetch();
                if (groupId) void groupMembers.refetch();
              }}
              disabled={isRefreshing}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#e4e7ec] bg-white px-3.5 text-[13px] font-medium text-[#1c1d1f] transition hover:bg-[#f4f5f6] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#266df0]"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
              Atualizar
            </button>
            <Link
              href="/importar"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#232529] px-4 text-[13px] font-medium text-white transition hover:bg-[#101113] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#266df0]"
            >
              <Upload className="h-3.5 w-3.5" />
              Importar
            </Link>
          </div>
        </section>

        <section aria-label="Resumo da base" className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-[#e4e7ec] pb-3 text-[12px] text-[#6f7988]">
          <span><strong className="font-semibold text-[#1c1d1f]">{studentsQuery.isLoading ? "—" : (riskSummary.data?.total_students ?? students.length).toLocaleString("pt-BR")}</strong> alunos na base</span>
          <span><strong className="font-semibold text-[#1c1d1f]">{studentsQuery.isLoading || riskSummary.isLoading ? "—" : highRisk.toLocaleString("pt-BR")}</strong> com risco elevado</span>
          <span><strong className="font-semibold text-[#1c1d1f]">{studentsQuery.isLoading || riskSummary.isLoading ? "—" : unclassified.toLocaleString("pt-BR")}</strong> sem classificação</span>
          <span className="text-[#9fa1a7]">Ausência de score não significa baixo risco</span>
        </section>

        <section className="overflow-hidden rounded-xl border border-[#e4e7ec] bg-white">
          <div className="border-b border-[#e4e7ec] p-4 sm:p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <label className="relative block min-w-0 flex-1">
                <span className="sr-only">Buscar por nome, matrícula ou curso</span>
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9fa1a7]" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Buscar por nome, matrícula ou curso"
                  className="h-10 w-full rounded-lg border border-[#e4e7ec] bg-white pl-10 pr-9 text-[13px] text-[#1c1d1f] outline-none placeholder:text-[#9fa1a7] focus:border-[#266df0] focus:ring-2 focus:ring-[#266df0]/15"
                />
                {query ? (
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    aria-label="Limpar busca"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-[#9fa1a7] hover:bg-[#f4f5f6] hover:text-[#1c1d1f]"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </label>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4 lg:w-auto lg:min-w-[520px]">
                <label className="block">
                  <span className="sr-only">Filtrar por risco</span>
                  <select
                    value={risk}
                    onChange={(e) => setRisk(e.target.value)}
                    className="h-10 w-full rounded-lg border border-[#e4e7ec] bg-white px-3 text-[13px] text-[#2e3238] outline-none focus:border-[#266df0] focus:ring-2 focus:ring-[#266df0]/15"
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
                    className="h-10 w-full rounded-lg border border-[#e4e7ec] bg-white px-3 text-[13px] text-[#2e3238] outline-none focus:border-[#266df0] focus:ring-2 focus:ring-[#266df0]/15"
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
                  <span className="sr-only">Filtrar por grupo</span>
                  <select
                    value={groupId}
                    onChange={(e) => applyGroup(e.target.value)}
                    className="h-10 w-full rounded-lg border border-[#e4e7ec] bg-white px-3 text-[13px] text-[#2e3238] outline-none focus:border-[#266df0] focus:ring-2 focus:ring-[#266df0]/15"
                  >
                    <option value="">Todos os grupos</option>
                    {(groupsCatalog.data?.groups || []).map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="sr-only">Ordenar alunos</span>
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value as StudentSort)}
                    className="h-10 w-full rounded-lg border border-[#e4e7ec] bg-white px-3 text-[13px] text-[#2e3238] outline-none focus:border-[#266df0] focus:ring-2 focus:ring-[#266df0]/15"
                  >
                    <option value="risk_desc">Maior score primeiro</option>
                    <option value="risk_asc">Menor score primeiro</option>
                    <option value="name_asc">Nome (A–Z)</option>
                  </select>
                </label>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2" role="tablist" aria-label="Segmentos de alunos">
              {(
                [
                  ["todos", "Todos"],
                  ["risco", "Risco elevado"],
                  ["sem_classificacao", "Sem classificação"],
                  ["dados_insuficientes", "Dados insuficientes"],
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
                    "rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#266df0]",
                    tab === value
                      ? "bg-[#266df0] text-white"
                      : "bg-[#f4f5f6] text-[#6f7988] hover:bg-[#EFF6FF] hover:text-[#266df0]"
                  )}
                >
                  {label}
                </button>
              ))}
              {hasFilters ? (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-[#6f7988] hover:text-[#1c1d1f]"
                >
                  <X className="h-3.5 w-3.5" />
                  Limpar filtros
                </button>
              ) : null}
            </div>
          </div>

          {studentsQuery.isLoading ? (
            <div className="space-y-3 p-5">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-[66px] w-full rounded-xl" />
              ))}
            </div>
          ) : null}

          {studentsQuery.isError ? (
            <div role="alert" className="m-4 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5">
              <p className="text-sm font-semibold text-[#B42318]">Não foi possível carregar os alunos.</p>
              <button type="button" onClick={() => void studentsQuery.refetch()} className="mt-3 text-sm font-semibold text-[#B42318] underline underline-offset-4">
                Tentar novamente
              </button>
            </div>
          ) : null}

          {!studentsQuery.isLoading && !studentsQuery.isError ? (
            <>
              <div className="flex flex-col gap-2 px-4 py-3 sm:px-5">
                <p className="text-[13px] font-semibold text-[#1c1d1f]">
                  Resultados
                  <span className="ml-1 font-normal text-[#9fa1a7]">
                    ({filtered.length.toLocaleString("pt-BR")})
                    {filtered.length > visibleLimit
                      ? ` · mostrando ${visibleLimit.toLocaleString("pt-BR")}`
                      : ""}
                  </span>
                </p>
                {groupId ? (
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#BFDBFE] bg-[#EFF6FF] px-3 py-2 text-[12px] text-[#407ff2]">
                    <Layers className="h-3.5 w-3.5 shrink-0" />
                    <span className="font-semibold">
                      Grupo:{" "}
                      {(groupsCatalog.data?.groups || []).find((g) => g.id === groupId)?.name || groupId}
                    </span>
                    {groupMembers.isLoading ? <span className="text-[#6f7988]">Carregando integrantes…</span> : null}
                    {groupMembers.isError ? (
                      <span className="text-[#B42318]">Não foi possível carregar os membros do grupo.</span>
                    ) : null}
                    {groupMembers.data ? (
                      <span className="text-[#2e3238]">
                        {groupMembers.data.size.toLocaleString("pt-BR")} com sinal ativo no grupo
                      </span>
                    ) : null}
                    <Link
                      href={"/alunos/grupos/" + encodeURIComponent(groupId)}
                      className="ml-auto font-semibold underline underline-offset-2"
                    >
                      Ver grupo
                    </Link>
                    <button type="button" onClick={() => applyGroup("")} className="font-medium text-[#6f7988] hover:text-[#1c1d1f]">
                      Limpar grupo
                    </button>
                  </div>
                ) : null}
                {tab === "dados_insuficientes" ? (
                  <p className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-3 py-2 text-[11px] leading-relaxed text-[#B54708]">
                    Segmento de cobertura: alunos sem score utilizável. Não representa baixo risco.
                  </p>
                ) : null}
              </div>

              {filtered.length === 0 ? (
                <div className="flex flex-col items-center px-5 py-14 text-center">
                  <span className="grid h-12 w-12 place-items-center rounded-xl bg-[#f4f5f6] text-[#6f7988]">
                    {hasFilters ? <Search className="h-5 w-5" /> : <Users className="h-5 w-5" />}
                  </span>
                  <h3 className="mt-4 text-[14px] font-semibold text-[#1c1d1f]">
                    {hasFilters ? "Nenhum aluno encontrado" : "Sua base começa aqui"}
                  </h3>
                  <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-[#6f7988]">
                    {hasFilters
                      ? "Tente ajustar os filtros ou remover alguns critérios."
                      : "Importe uma planilha para começar a análise de risco."}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[980px] text-left">
                    <thead className="border-y border-[#e4e7ec] bg-white text-[11px] font-medium text-[#6f7988]">
                      <tr>
                        <th className="px-5 py-3 font-medium">Aluno</th>
                        <th className="px-4 py-3 font-medium">Matrícula</th>
                        <th className="px-4 py-3 font-medium">Curso</th>
                        <th className="px-4 py-3 font-medium">Classificação</th>
                        <th className="px-4 py-3 text-right font-medium">Score</th>
                        <th className="px-4 py-3 font-medium">Acompanhamento</th>
                        <th className="w-10 px-3 py-3" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e4e7ec]">
                      {visibleStudents.map((student) => {
                        const signal = primarySignal(student);
                        const log = latestLogs.get(student.id);
                        return (
                          <tr key={student.id} className="group transition-colors hover:bg-[#f4f5f6]">
                            <td className="px-5 py-3">
                              <div className="flex min-w-0 items-center gap-3">
                                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#f4f5f6] text-[11px] font-semibold text-[#505967]">
                                  {initials(student.nome)}
                                </span>
                                <div className="min-w-0">
                                  <Link href={`/alunos/${student.id}`} className="block truncate text-[13px] font-medium text-[#1c1d1f] hover:text-[#266df0]">
                                    {student.nome || "Sem nome"}
                                  </Link>
                                  <p className="mt-0.5 max-w-[280px] truncate text-[11px] text-[#9fa1a7]">
                                    {signal.signal || signal.empty}
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-[12px] tabular-nums text-[#505967]">{student.matricula || "—"}</td>
                            <td className="max-w-[220px] truncate px-4 py-3 text-[12px] text-[#505967]">{student.curso || "—"}</td>
                            <td className="px-4 py-3"><RiskBadge level={student.risk_level} /></td>
                            <td className="px-4 py-3 text-right text-[12px] font-medium tabular-nums text-[#1c1d1f]">{student.risk_score != null ? formatScore(student.risk_score) : "—"}</td>
                            <td className="px-4 py-3 text-[12px] text-[#6f7988]">{log ? followUpLabel(log.status) : "Sem contato registrado"}</td>
                            <td className="px-3 py-3 text-right">
                              <button type="button" onClick={() => setSelectedId(student.id)} aria-label={`Visualizar ${student.nome || "aluno"}`} className="rounded-md p-1.5 text-[#9fa1a7] opacity-0 transition hover:bg-white hover:text-[#1c1d1f] group-hover:opacity-100 focus:opacity-100">
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

              {filtered.length > visibleLimit ? (
                <div className="border-t border-[#e4e7ec] px-4 py-4 sm:px-5">
                  <button
                    type="button"
                    onClick={() => setVisibleLimit((n) => n + 50)}
                    className="inline-flex h-10 w-full items-center justify-center rounded-lg border border-[#e4e7ec] bg-white text-[13px] font-semibold text-[#2e3238] transition hover:bg-[#f4f5f6] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#266df0]"
                  >
                    Carregar mais ({Math.min(50, filtered.length - visibleLimit)} de{" "}
                    {(filtered.length - visibleLimit).toLocaleString("pt-BR")} restantes)
                  </button>
                </div>
              ) : null}
            </>
          ) : null}
        </section>
      </main>

      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}
