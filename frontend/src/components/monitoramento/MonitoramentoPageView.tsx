"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Info,
  RefreshCw,
  TrendingUp,
  Users,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Skeleton } from "@/components/ui/skeleton";
import { RiskBadge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RetentionAnalyticsPanel } from "@/components/monitoramento/retention-analytics-panel";
import {
  CHANGE_LABEL,
  CurrentRiskDistribution,
  DistributionTimeline,
  Metric,
  ScoreTimeline,
  StudentAssessmentTimeline,
  dateLabel,
  dateTimeLabel,
  movementTone,
  scoreLabel,
  type Period,
} from "@/components/monitoramento/monitoramento-charts";

export function MonitoramentoPageView() {
  const [period, setPeriod] = useState<Period>("90");
  const [course, setCourse] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [to, setTo] = useState(() => new Date().toISOString());
  const from = useMemo(
    () => new Date(new Date(to).getTime() - Number(period) * 86400000).toISOString(),
    [period, to]
  );

  const historyQuery = useQuery({
    queryKey: ["risk-history", period, course, riskLevel, from, to],
    queryFn: () =>
      api.riskHistory({
        from,
        to,
        course: course || undefined,
        risk_level: riskLevel || undefined,
        page: 1,
        page_size: 50,
      }),
    retry: false,
  });

  const summaryQuery = useQuery({
    queryKey: ["risk-summary-monitor"],
    queryFn: () => api.riskSummary(),
    retry: false,
  });

  const workQuery = useQuery({
    queryKey: ["retention-work-summary-monitor"],
    queryFn: () => api.retentionWorkSummary(),
    retry: false,
  });

  const selectedHistoryQuery = useQuery({
    queryKey: ["student-risk-history", selectedStudentId, from, to],
    queryFn: () =>
      api.studentRiskHistory(selectedStudentId!, { from, to, page: 1, page_size: 200 }),
    enabled: Boolean(selectedStudentId),
    retry: false,
  });

  const data = historyQuery.data;
  const courseOptions = data?.courses ?? [];
  const refresh = () => setTo(new Date().toISOString());
  const counts = data?.comparison_counts;
  const movements = data?.movements ?? [];
  const summary = summaryQuery.data?.summary;

  return (
    <>
      <Header title="Monitoramento de risco" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-4 border-b border-[#E5E7EB] pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#2563EB]">
              <Activity className="h-3.5 w-3.5" />
              Inteligência temporal
            </div>
            <h1 className="text-[24px] font-semibold tracking-[-0.035em] text-[#101828]">
              Monitoramento de risco
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">
              Distribuição atual, evolução entre avaliações reais, analytics de intervenções e fatores
              preservados — sem inferir causalidade.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="risk-period">
              Período
            </label>
            <select
              id="risk-period"
              value={period}
              onChange={(e) => setPeriod(e.target.value as Period)}
              className="h-10 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-medium text-[#344054]"
            >
              <option value="30">Últimos 30 dias</option>
              <option value="90">Últimos 90 dias</option>
              <option value="180">Últimos 180 dias</option>
              <option value="365">Últimos 365 dias</option>
            </select>
            <button
              type="button"
              onClick={refresh}
              disabled={historyQuery.isFetching}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-medium text-[#344054] hover:bg-[#F9FAFB] disabled:opacity-60"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", historyQuery.isFetching && "animate-spin")} />
              Atualizar
            </button>
            <Link
              href="/alunos"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-3.5 text-[12px] font-semibold text-white hover:bg-[#1D4ED8]"
            >
              Lista de alunos
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>

        <section className="flex flex-wrap items-end gap-3 rounded-xl border border-[#E5E7EB] bg-white p-4">
          <label className="flex min-w-[180px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">
            Curso
            <select
              value={course}
              onChange={(e) => setCourse(e.target.value)}
              className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-2.5 text-[12px] text-[#344054]"
            >
              <option value="">Todos os cursos</option>
              {courseOptions.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[180px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">
            Classificação
            <select
              value={riskLevel}
              onChange={(e) => setRiskLevel(e.target.value)}
              className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-2.5 text-[12px] text-[#344054]"
            >
              <option value="">Todos os níveis</option>
              <option value="critico">Crítico</option>
              <option value="medio">Moderado</option>
              <option value="baixo">Baixo</option>
            </select>
          </label>
          <div className="flex items-center gap-2 pb-2 text-[11px] text-[#667085]">
            <CalendarDays className="h-3.5 w-3.5" />
            {data
              ? dateLabel(data.period.from) + " – " + dateLabel(data.period.to)
              : "Últimos " + period + " dias"}{" "}
            · avaliações reais
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]">
          <div className="rounded-xl border border-[#E5E7EB] bg-white p-5">
            <div className="mb-4">
              <h2 className="text-[14px] font-semibold text-[#101828]">Distribuição atual de risco</h2>
              <p className="mt-1 text-[11px] text-[#667085]">Snapshot da base — independente do período histórico.</p>
            </div>
            {summaryQuery.isLoading && <Skeleton className="h-36 rounded-lg" />}
            {summaryQuery.isError && (
              <p className="rounded-lg border border-[#FECDCA] bg-[#FEF3F2] p-3 text-[12px] text-[#B42318]">
                Não foi possível carregar o resumo de risco atual.
              </p>
            )}
            {summary && (
              <CurrentRiskDistribution
                summary={summary}
                totalStudents={summaryQuery.data?.total_students}
                totalScored={summaryQuery.data?.total_scored}
              />
            )}
          </div>
          <div className="rounded-xl border border-[#E5E7EB] bg-white p-5">
            <div className="mb-4">
              <h2 className="text-[14px] font-semibold text-[#101828]">Fila operacional</h2>
              <p className="mt-1 text-[11px] text-[#667085]">Pendências de retenção — não desfechos de evasão.</p>
            </div>
            {workQuery.isLoading && <Skeleton className="h-28 rounded-lg" />}
            {workQuery.isError && (
              <p className="text-[12px] text-[#B42318]">Resumo operacional indisponível.</p>
            )}
            {workQuery.data && (
              <div className="space-y-3">
                <Metric label="Pendentes" value={workQuery.data.pending} hint="Ainda não concluídos" icon={<Users className="h-4 w-4" />} />
                <Metric
                  label={"Atrasados (>" + workQuery.data.overdue_policy_hours + "h)"}
                  value={workQuery.data.overdue_48h}
                  hint="Política de atraso da instituição"
                  icon={<ArrowUpRight className="h-4 w-4" />}
                  tone="danger"
                />
                <Metric label="Falhas" value={workQuery.data.failed} hint="Execuções com erro" icon={<Info className="h-4 w-4" />} />
                <Link href="/trabalho" className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#175CD3]">
                  Central de Trabalho <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>
        </section>

        <RetentionAnalyticsPanel days={Number(period)} />

        {historyQuery.isError && (
          <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5">
            <p className="text-[13px] font-semibold text-[#B42318]">Não foi possível carregar o histórico de risco.</p>
            <button onClick={refresh} className="mt-3 text-[12px] font-semibold text-[#B42318] underline">
              Tentar novamente
            </button>
          </div>
        )}

        {historyQuery.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[1, 2, 3, 4].map((n) => (
              <Skeleton key={n} className="h-28 rounded-xl" />
            ))}
          </div>
        ) : (
          data && (
            <>
              <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <Metric label="Avaliações registradas" value={data.total_assessments} hint="Eventos no período" icon={<Activity className="h-4 w-4" />} />
                <Metric label="Risco aumentou" value={counts?.increased ?? 0} hint="Mesma versão e escopo" icon={<ArrowUpRight className="h-4 w-4" />} tone="danger" />
                <Metric label="Risco diminuiu" value={counts?.decreased ?? 0} hint="Mesma versão e escopo" icon={<ArrowDownRight className="h-4 w-4" />} tone="success" />
                <Metric label="Mudança de classificação" value={counts?.classification_changed ?? 0} hint="Transição confirmada" icon={<TrendingUp className="h-4 w-4" />} />
                <Metric
                  label="Sem histórico comparável"
                  value={(counts?.no_comparable_history ?? 0) + (counts?.model_changed ?? 0)}
                  hint="Sem anterior ou versão incompatível"
                  icon={<Users className="h-4 w-4" />}
                />
              </section>

              {data.temporal_data_truncated && (
                <p className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] p-3 text-[12px] text-[#B54708]">
                  Série temporal limitada aos registros mais recentes; totais podem estar parciais.
                </p>
              )}

              <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]">
                <div className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                  <div className="mb-4">
                    <h2 className="text-[14px] font-semibold text-[#101828]">Evolução dos scores</h2>
                    <p className="mt-1 text-[11px] text-[#667085]">Média semanal por versão do modelo</p>
                  </div>
                  <ScoreTimeline data={data.timeline} />
                </div>
                <div className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                  <div className="mb-4">
                    <h2 className="text-[14px] font-semibold text-[#101828]">Distribuição histórica</h2>
                    <p className="mt-1 text-[11px] text-[#667085]">Avaliação representativa por aluno/semana</p>
                  </div>
                  <DistributionTimeline data={data.timeline} />
                </div>
              </section>

              <section className="overflow-hidden rounded-xl border border-[#E5E7EB] bg-white">
                <div className="border-b border-[#EAECF0] p-5">
                  <h2 className="text-[14px] font-semibold text-[#101828]">Movimentações de risco</h2>
                  <p className="mt-1 text-[11px] text-[#667085]">
                    Comparação entre avaliações. Aumento não prova evasão nem causalidade.
                  </p>
                </div>
                {movements.length === 0 ? (
                  <div className="p-10 text-center text-[13px] text-[#667085]">
                    Nenhuma movimentação no período. Ausência de histórico ≠ estabilidade.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[860px] text-left">
                      <thead className="bg-[#F9FAFB] text-[10px] font-semibold uppercase text-[#667085]">
                        <tr>
                          <th className="px-5 py-3">Aluno</th>
                          <th className="px-3 py-3">Anterior</th>
                          <th className="px-3 py-3">Atual</th>
                          <th className="px-3 py-3">Variação</th>
                          <th className="px-3 py-3">Movimento</th>
                          <th className="px-5 py-3">Última avaliação</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#EAECF0]">
                        {movements.map((m) => (
                          <tr key={m.student_id} className="hover:bg-[#F9FAFB]">
                            <td className="px-5 py-3.5">
                              <button
                                type="button"
                                onClick={() => setSelectedStudentId(m.student_id)}
                                className="text-left text-[12px] font-semibold text-[#175CD3] hover:underline"
                              >
                                {m.student_name || m.matricula || "Aluno"}
                              </button>
                            </td>
                            <td className="px-3 py-3.5 text-[12px]">{scoreLabel(m.previous_score)}</td>
                            <td className="px-3 py-3.5 text-[12px] font-semibold">
                              {scoreLabel(m.current_score)}
                              <div className="mt-1">
                                <RiskBadge level={m.current_risk_level} />
                              </div>
                            </td>
                            <td className="px-3 py-3.5 text-[12px] font-semibold">
                              {m.delta == null ? "—" : (m.delta > 0 ? "+" : "") + scoreLabel(m.delta)}
                            </td>
                            <td className="px-3 py-3.5">
                              <span className={cn("inline-flex rounded-full px-2 py-1 text-[10px] font-medium", movementTone(m.change_type))}>
                                {CHANGE_LABEL[m.change_type]}
                              </span>
                            </td>
                            <td className="px-5 py-3.5 text-[11px] text-[#667085]">
                              {dateTimeLabel(m.current_evaluated_at)}
                              <Link href={"/alunos/" + m.student_id} className="mt-1 block text-[10px] font-semibold text-[#175CD3]">
                                Ficha
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {selectedStudentId && (
                <section className="rounded-xl border border-[#B2CCFF] bg-white p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-[14px] font-semibold text-[#101828]">Trajetória do aluno</h2>
                      <p className="mt-1 text-[11px] text-[#667085]">
                        {selectedHistoryQuery.data?.student.name || "Carregando…"}
                      </p>
                    </div>
                    <button type="button" onClick={() => setSelectedStudentId(null)} className="text-[11px] text-[#667085]">
                      Fechar
                    </button>
                  </div>
                  {selectedHistoryQuery.isLoading && <Skeleton className="mt-4 h-20 rounded-lg" />}
                  {selectedHistoryQuery.isError && (
                    <p className="mt-4 text-[12px] text-[#B42318]">Falha ao carregar trajetória.</p>
                  )}
                  {selectedHistoryQuery.data && (
                    <>
                      <StudentAssessmentTimeline assessments={selectedHistoryQuery.data.assessments} />
                      <div className="grid gap-4 md:grid-cols-2">
                        <div>
                          <h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Avaliações e fatores</h3>
                          {selectedHistoryQuery.data.assessments.length === 0 && (
                            <p className="text-[12px] text-[#667085]">Sem avaliações no período.</p>
                          )}
                          {selectedHistoryQuery.data.assessments.map((a) => (
                            <div key={a.id} className="mb-2 rounded-lg border border-[#EAECF0] p-3">
                              <div className="flex justify-between gap-2">
                                <span className="text-[12px] font-semibold">Score {scoreLabel(a.score)}</span>
                                <RiskBadge level={a.risk_level} />
                              </div>
                              <p className="mt-1 text-[10px] text-[#667085]">{dateTimeLabel(a.evaluated_at)}</p>
                              {a.explanation_available && a.explanation?.top_factors?.length ? (
                                <ul className="mt-2 list-disc pl-4 text-[11px] text-[#475467]">
                                  {a.explanation.top_factors.map((f, i) => (
                                    <li key={a.id + "-" + i}>{f.label || f.feature || "Fator"}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-2 text-[10px] text-[#667085]">Fatores não preservados nesta avaliação.</p>
                              )}
                            </div>
                          ))}
                        </div>
                        <div>
                          <h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Intervenções</h3>
                          {selectedHistoryQuery.data.interventions.length === 0 && (
                            <p className="text-[12px] text-[#667085]">Nenhuma no período.</p>
                          )}
                          {selectedHistoryQuery.data.interventions.map((i) => (
                            <div key={i.id} className="mb-2 rounded-lg border border-[#EAECF0] p-3 text-[12px]">
                              <p className="font-medium">
                                {i.channel || "Canal n/d"} · {i.status}
                              </p>
                              <p className="mt-1 text-[10px] text-[#667085]">{dateTimeLabel(i.created_at)}</p>
                              <p className="mt-1 text-[10px] text-[#475467]">
                                Desfecho: {i.outcome || "Ainda não registrado"}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </section>
              )}
            </>
          )
        )}
      </main>
    </>
  );
}
