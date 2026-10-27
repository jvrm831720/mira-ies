"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CircleHelp,
  Info,
  RefreshCw,
  Users,
  ChevronRight,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { StudentDrawer } from "@/components/students/student-drawer";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn, formatScore } from "@/lib/utils";

type RiskFilter = "" | "critico" | "medio" | "baixo";

function initials(name?: string | null) {
  if (!name?.trim()) return "—";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toLocaleUpperCase("pt-BR");
}

export default function MonitoramentoPage() {
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["risk-summary", "monitoramento"],
    queryFn: () => api.riskSummary(),
    retry: false,
  });
  const criticalQuery = useQuery({
    queryKey: ["risk-critical", "monitoramento"],
    queryFn: () => api.riskCritical(50),
    retry: false,
  });
  const studentsQuery = useQuery({
    queryKey: ["students", "monitoramento"],
    queryFn: () => api.students({ limit: 200 }),
    retry: false,
  });
  const logsQuery = useQuery({
    queryKey: ["retention-logs", "monitoramento"],
    queryFn: () => api.retentionLogs({ limit: 100 }),
    retry: false,
  });

  const summary = summaryQuery.data?.summary;
  const totalStudents =
    summaryQuery.data?.total_students ?? studentsQuery.data?.students.length ?? 0;
  const totalScored = summaryQuery.data?.total_scored;
  const critico = summary?.critico ?? 0;
  const medio = summary?.medio ?? 0;
  const baixo = summary?.baixo ?? 0;
  const semScore = summary?.sem_score ?? 0;
  const elevated = critico + medio;

  const scoredForBar = critico + medio + baixo;
  const pct = (n: number) =>
    scoredForBar > 0 ? Math.round((n / scoredForBar) * 1000) / 10 : 0;

  const withFollowUp = useMemo(() => {
    const set = new Set<string>();
    for (const log of logsQuery.data?.logs || []) {
      if (log.student_id) set.add(log.student_id);
    }
    return set;
  }, [logsQuery.data]);

  const priorityQueue = useMemo(() => {
    const fromCritical = criticalQuery.data?.students ?? [];
    const fromStudents = (studentsQuery.data?.students ?? []).filter((s) =>
      ["critico", "medio"].includes(s.risk_level || "")
    );

    const byId = new Map<string, (typeof fromStudents)[number]>();
    for (const s of fromStudents) byId.set(s.id, s);
    for (const s of fromCritical) {
      if (!byId.has(s.id)) {
        byId.set(s.id, {
          id: s.id,
          nome: s.nome,
          matricula: s.matricula,
          curso: s.curso,
          risk_level: s.risk_level,
          risk_score: s.risk_score,
        });
      }
    }

    let list = [...byId.values()];
    if (riskFilter) {
      list = list.filter((s) => s.risk_level === riskFilter);
    }

    list.sort((a, b) => {
      const levelRank = (l?: string | null) =>
        l === "critico" ? 0 : l === "medio" ? 1 : 2;
      const lr = levelRank(a.risk_level) - levelRank(b.risk_level);
      if (lr !== 0) return lr;
      const sa = a.risk_score;
      const sb = b.risk_score;
      if (sa == null && sb == null)
        return (a.nome || "").localeCompare(b.nome || "", "pt-BR");
      if (sa == null) return 1;
      if (sb == null) return -1;
      return sb - sa;
    });

    return list;
  }, [criticalQuery.data, studentsQuery.data, riskFilter]);

  const isLoading =
    summaryQuery.isLoading || criticalQuery.isLoading || studentsQuery.isLoading;
  const isRefreshing =
    summaryQuery.isFetching ||
    criticalQuery.isFetching ||
    studentsQuery.isFetching ||
    logsQuery.isFetching;

  function refetchAll() {
    void summaryQuery.refetch();
    void criticalQuery.refetch();
    void studentsQuery.refetch();
    void logsQuery.refetch();
  }

  const hardError =
    summaryQuery.isError && criticalQuery.isError && studentsQuery.isError;

  return (
    <>
      <Header title="Monitoramento" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-3 border-b border-[#E5E7EB] pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-[22px] font-semibold tracking-[-0.03em] text-[#111827] sm:text-[24px]">
              Monitoramento de risco
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">
              Acompanhe a situação atual da base e priorize alunos que exigem atenção. A
              comparação temporal de scores depende de histórico de avaliações ainda não
              disponível nesta API.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refetchAll}
              disabled={isRefreshing}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#111827] transition hover:bg-[#F8FAFC] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
              Atualizar
            </button>
            <Link
              href="/alunos"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-4 text-[13px] font-semibold text-white transition hover:bg-[#1D4ED8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              Lista de alunos
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>

        {hardError && (
          <div
            role="alert"
            className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-6 text-center"
          >
            <p className="text-[15px] font-semibold text-[#111827]">
              Não foi possível carregar o monitoramento.
            </p>
            <p className="mt-1 text-[13px] text-[#667085]">
              Verifique a conexão e tente novamente.
            </p>
            <button
              type="button"
              onClick={refetchAll}
              className="mt-3 text-[13px] font-semibold text-[#B42318] underline underline-offset-4"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {!hardError && (
          <>
            <section
              aria-label="Indicadores atuais"
              className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
            >
              <Kpi
                label="Alunos na base"
                value={isLoading ? "—" : totalStudents.toLocaleString("pt-BR")}
                hint={
                  totalScored != null
                    ? `${totalScored.toLocaleString("pt-BR")} com avaliação de risco`
                    : "Total retornado pelo resumo ou lista"
                }
                icon={<Users className="h-4 w-4" />}
                tone="neutral"
              />
              <Kpi
                label="Atenção prioritária"
                value={isLoading ? "—" : elevated.toLocaleString("pt-BR")}
                hint="Classificação crítica ou moderada (situação atual)"
                icon={<AlertTriangle className="h-4 w-4" />}
                tone="coral"
              />
              <Kpi
                label="Sem classificação"
                value={isLoading ? "—" : semScore.toLocaleString("pt-BR")}
                hint="Sem score — não é baixo risco"
                icon={<CircleHelp className="h-4 w-4" />}
                tone="blue"
              />
              <Kpi
                label="Com registro de contato"
                value={
                  logsQuery.isLoading
                    ? "—"
                    : logsQuery.isError
                      ? "—"
                      : withFollowUp.size.toLocaleString("pt-BR")
                }
                hint={
                  logsQuery.isError
                    ? "Histórico de contatos indisponível"
                    : "Alunos com ao menos um log de retenção"
                }
                icon={<Activity className="h-4 w-4" />}
                tone="neutral"
              />
            </section>

            <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-[15px] font-semibold text-[#111827]">
                    Distribuição atual de risco
                  </h2>
                  <p className="mt-1 text-[12px] text-[#667085]">
                    Baseada na última avaliação disponível por aluno. Não é uma série
                    temporal.
                  </p>
                </div>
                {summaryQuery.isError && (
                  <span className="text-[12px] text-[#B54708]">
                    Resumo parcial ou indisponível
                  </span>
                )}
              </div>

              {summaryQuery.isLoading ? (
                <Skeleton className="mt-4 h-10 w-full rounded-lg" />
              ) : scoredForBar === 0 ? (
                <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">
                  Ainda não há alunos com classificação de risco para montar a distribuição.
                </p>
              ) : (
                <>
                  <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-[#F8FAFC]">
                    {critico > 0 && (
                      <div
                        className="bg-[#F04438]"
                        style={{ width: `${(critico / scoredForBar) * 100}%` }}
                        title={`Crítico: ${critico}`}
                      />
                    )}
                    {medio > 0 && (
                      <div
                        className="bg-[#FDB022]"
                        style={{ width: `${(medio / scoredForBar) * 100}%` }}
                        title={`Moderado: ${medio}`}
                      />
                    )}
                    {baixo > 0 && (
                      <div
                        className="bg-[#12B76A]"
                        style={{ width: `${(baixo / scoredForBar) * 100}%` }}
                        title={`Baixo: ${baixo}`}
                      />
                    )}
                  </div>
                  <ul className="mt-4 grid gap-2 sm:grid-cols-3">
                    <LegendItem
                      color="#F04438"
                      label="Crítico"
                      count={critico}
                      pct={pct(critico)}
                    />
                    <LegendItem
                      color="#FDB022"
                      label="Moderado"
                      count={medio}
                      pct={pct(medio)}
                    />
                    <LegendItem
                      color="#12B76A"
                      label="Baixo"
                      count={baixo}
                      pct={pct(baixo)}
                    />
                  </ul>
                  {semScore > 0 && (
                    <p className="mt-3 text-[12px] text-[#667085]">
                      + {semScore.toLocaleString("pt-BR")} aluno(s) sem score (fora da barra).
                    </p>
                  )}
                </>
              )}
            </section>

            <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#EFF6FF] text-[#2563EB]">
                  <Info className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <h2 className="text-[15px] font-semibold text-[#111827]">
                    Evolução e mudanças de risco
                  </h2>
                  <p className="mt-1 text-[13px] leading-relaxed text-[#667085]">
                    Não há endpoint de histórico de avaliações de score neste produto. Por
                    isso, esta tela{" "}
                    <strong className="font-semibold text-[#344054]">
                      não mostra piora, melhora nem tendências temporais
                    </strong>
                    — isso exigiria persistir cada avaliação (aluno, tenant, score, nível,
                    data, versão do modelo) e expor uma API de série ou de deltas.
                  </p>
                  <p className="mt-2 text-[12px] text-[#98A2B3]">
                    Até lá, use a fila de atenção abaixo com a classificação{" "}
                    <em>atual</em>, sem interpretar variação no tempo.
                  </p>
                </div>
              </div>
            </section>

            <section className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white">
              <div className="flex flex-col gap-3 border-b border-[#E5E7EB] p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
                <div>
                  <h2 className="text-[15px] font-semibold text-[#111827]">
                    Fila de atenção (situação atual)
                  </h2>
                  <p className="mt-1 text-[12px] text-[#667085]">
                    Ordenada por nível (crítico → moderado) e score decrescente. Sem score
                    fica depois dos classificados. Não indica piora recente.
                  </p>
                </div>
                <label className="block sm:w-48">
                  <span className="sr-only">Filtrar por risco</span>
                  <select
                    value={riskFilter}
                    onChange={(e) => setRiskFilter(e.target.value as RiskFilter)}
                    className="h-10 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 text-[13px] text-[#344054] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"
                  >
                    <option value="">Crítico e moderado</option>
                    <option value="critico">Somente crítico</option>
                    <option value="medio">Somente moderado</option>
                  </select>
                </label>
              </div>

              {(criticalQuery.isLoading || studentsQuery.isLoading) && (
                <div className="space-y-3 p-5">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-14 w-full rounded-lg" />
                  ))}
                </div>
              )}

              {!criticalQuery.isLoading &&
                !studentsQuery.isLoading &&
                priorityQueue.length === 0 && (
                  <div className="flex flex-col items-center px-5 py-12 text-center">
                    <span className="grid h-12 w-12 place-items-center rounded-xl bg-[#F8FAFC] text-[#667085]">
                      <Users className="h-5 w-5" />
                    </span>
                    <h3 className="mt-4 text-[14px] font-semibold text-[#111827]">
                      Nenhum aluno nesta fila
                    </h3>
                    <p className="mt-1 max-w-sm text-[13px] text-[#667085]">
                      {riskFilter
                        ? "Ajuste o filtro ou consulte a lista completa de alunos."
                        : "Não há alunos com classificação crítica ou moderada neste momento."}
                    </p>
                    <Link
                      href="/alunos"
                      className="mt-4 text-[13px] font-semibold text-[#2563EB] hover:text-[#1D4ED8]"
                    >
                      Ir para lista de alunos
                    </Link>
                  </div>
                )}

              {priorityQueue.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-left">
                    <thead className="bg-[#F8FAFC] text-[11px] font-semibold uppercase tracking-[0.04em] text-[#667085]">
                      <tr>
                        <th className="px-5 py-3">Aluno</th>
                        <th className="px-4 py-3">Curso</th>
                        <th className="px-4 py-3">Risco</th>
                        <th className="px-4 py-3">Acompanhamento</th>
                        <th className="px-4 py-3">
                          <span className="sr-only">Abrir</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E5E7EB]">
                      {priorityQueue.map((student) => {
                        const hasLog = withFollowUp.has(student.id);
                        return (
                          <tr key={student.id} className="hover:bg-[#F8FAFC]">
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
                                    {student.matricula || "—"}
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
                              <span
                                className={cn(
                                  "inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium",
                                  hasLog
                                    ? "bg-[#EFF6FF] text-[#1D4ED8]"
                                    : "bg-[#F8FAFC] text-[#667085]"
                                )}
                              >
                                {hasLog ? "Com registro" : "Sem registro"}
                              </span>
                            </td>
                            <td className="px-4 py-3.5">
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => setSelectedId(student.id)}
                                  aria-label={`Abrir ficha rápida de ${student.nome || "aluno"}`}
                                  className="grid h-8 w-8 place-items-center rounded-lg text-[#98A2B3] hover:bg-white hover:text-[#2563EB] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                                >
                                  <ChevronRight className="h-4 w-4" />
                                </button>
                                <Link
                                  href={`/alunos/${student.id}`}
                                  className="text-[11px] font-semibold text-[#2563EB] hover:text-[#1D4ED8]"
                                >
                                  Ficha
                                </Link>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="border-t border-[#E5E7EB] bg-[#F8FAFC] px-4 py-3 text-[11px] text-[#667085] sm:px-5">
                {priorityQueue.length} aluno(s) na fila · dados atuais, sem comparação
                histórica
              </div>
            </section>
          </>
        )}
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

function Kpi({
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

function LegendItem({
  color,
  label,
  count,
  pct,
}: {
  color: string;
  label: string;
  count: number;
  pct: number;
}) {
  return (
    <li className="flex items-center gap-2 text-[13px] text-[#344054]">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      <span className="font-medium">{label}</span>
      <span className="tabular-nums text-[#667085]">
        {count.toLocaleString("pt-BR")} ({pct}%)
      </span>
    </li>
  );
}
