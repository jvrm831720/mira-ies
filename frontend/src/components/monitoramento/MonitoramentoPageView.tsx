"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  RefreshCw,
  TrendingUp,
  Users,
} from "@/components/ui/icons";
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
import {
  ComparabilityBadge,
  ModelVersionCell,
  AssessmentModelLine,
} from "@/components/monitoramento/comparability";
import type { RiskMovement } from "@/types/api";

type MovementFilter =
  | ""
  | "risco_aumentou"
  | "risco_diminuiu"
  | "mudanca_modelo"
  | "sem_historico_comparavel"
  | "classification_changed";

const PERIOD_VALUES: Period[] = ["30", "90", "180", "365"];

function MonitoramentoPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [period, setPeriod] = useState<Period>(() => {
    const p = searchParams.get("period") || "";
    return PERIOD_VALUES.includes(p as Period) ? (p as Period) : "90";
  });
  const [course, setCourse] = useState(() => searchParams.get("course") || "");
  const [riskLevel, setRiskLevel] = useState(() => {
    const r = searchParams.get("risk") || searchParams.get("risk_level") || "";
    return ["critico", "medio", "baixo"].includes(r) ? r : "";
  });
  const [movementFilter, setMovementFilter] = useState<MovementFilter>(() => {
    const m = searchParams.get("movement") || "";
    if (
      [
        "risco_aumentou",
        "risco_diminuiu",
        "mudanca_modelo",
        "sem_historico_comparavel",
        "classification_changed",
      ].includes(m)
    ) {
      return m as MovementFilter;
    }
    return "";
  });
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [to, setTo] = useState(() => new Date().toISOString());
  const [historyPage, setHistoryPage] = useState(1);
  const [extraMovements, setExtraMovements] = useState<RiskMovement[]>([]);

  const from = useMemo(
    () => new Date(new Date(to).getTime() - Number(period) * 86400000).toISOString(),
    [period, to]
  );

  useEffect(() => {
    const params = new URLSearchParams();
    if (period !== "90") params.set("period", period);
    if (course) params.set("course", course);
    if (riskLevel) params.set("risk", riskLevel);
    if (movementFilter) params.set("movement", movementFilter);
    const qs = params.toString();
    const next = qs ? pathname + "?" + qs : pathname;
    router.replace(next, { scroll: false });
  }, [period, course, riskLevel, movementFilter, pathname, router]);

  useEffect(() => {
    setHistoryPage(1);
    setExtraMovements([]);
  }, [period, course, riskLevel, from, to]);

  const historyQuery = useQuery({
    queryKey: ["risk-history", period, course, riskLevel, from, to, historyPage],
    queryFn: () =>
      api.riskHistory({
        from,
        to,
        course: course || undefined,
        risk_level: riskLevel || undefined,
        page: historyPage,
        page_size: 50,
      }),
    retry: false,
  });

  // Preserve all fetched pages: React Query replaces data when the page key changes.
  // Accumulate page 1 as the initial list, then append unseen students from later pages.
  useEffect(() => {
    const pageMovements = historyQuery.data?.movements;
    if (!pageMovements) return;

    setExtraMovements((previous) => {
      if (historyPage === 1) return pageMovements;

      const byStudent = new Map(previous.map((movement) => [movement.student_id, movement]));
      for (const movement of pageMovements) {
        if (!byStudent.has(movement.student_id)) {
          byStudent.set(movement.student_id, movement);
        }
      }
      return Array.from(byStudent.values());
    });
  }, [historyQuery.data, historyPage]);

  const summaryQuery = useQuery({
    queryKey: ["risk-summary-monitor"],
    queryFn: () => api.riskSummary(),
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
  const refresh = () => {
    setHistoryPage(1);
    setExtraMovements([]);
    setTo(new Date().toISOString());
  };
  const counts = data?.comparison_counts;
  const baseMovements = data?.movements ?? [];
  const movements = useMemo(() => {
    const list =
      extraMovements.length === 0
        ? baseMovements
        : Array.from(
            new Map(
              [...baseMovements, ...extraMovements].map((m) => [m.student_id, m] as const)
            ).values()
          );
    if (!movementFilter) return list;
    if (movementFilter === "classification_changed") {
      return list.filter((m) => m.classification_changed);
    }
    return list.filter((m) => m.change_type === movementFilter);
  }, [baseMovements, extraMovements, movementFilter]);

  const canLoadMore =
    Boolean(data?.pagination) &&
    (data?.pagination.page ?? 1) < (data?.pagination.pages ?? 1);
  const summary = summaryQuery.data?.summary;

  return (
    <>
      <Header title="Monitoramento de risco" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-4 border-b border-[#E4E7EC] pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#266DF0]">
              <Activity className="h-3.5 w-3.5" />
              Inteligência temporal
            </div>
            <h1 className="text-[24px] font-semibold tracking-[-0.035em] text-[#101828]">
              Monitoramento de risco
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">
              Evolução temporal das avaliações de risco persistidas: scores, movimentações entre níveis
              e trajetória por aluno. A fila operacional fica na Visão geral e na Central de Trabalho.
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
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-medium text-[#344054] hover:bg-[#F8F9FA] disabled:opacity-60"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", historyQuery.isFetching && "animate-spin")} />
              Atualizar
            </button>
            <Link
              href="/alunos"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#232529] px-3.5 text-[12px] font-medium text-white hover:bg-[#101112]"
            >
              Lista de alunos
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>

        <section className="flex flex-wrap items-end gap-3 rounded-[10px] border border-[#E4E7EC] bg-white p-4">
          <label className="flex min-w-[160px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">
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
          <label className="flex min-w-[160px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">
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
          <label className="flex min-w-[200px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">
            Movimentação
            <select
              value={movementFilter}
              onChange={(e) => setMovementFilter(e.target.value as MovementFilter)}
              className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-2.5 text-[12px] text-[#344054]"
            >
              <option value="">Todas as movimentações</option>
              <option value="risco_aumentou">Risco aumentou</option>
              <option value="risco_diminuiu">Risco diminuiu</option>
              <option value="classification_changed">Mudança de nível</option>
              <option value="mudanca_modelo">Mudança de modelo</option>
              <option value="sem_historico_comparavel">Sem histórico comparável</option>
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

        <section className="rounded-[10px] border border-[#E4E7EC] bg-white p-5">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-[14px] font-semibold text-[#101828]">Distribuição atual de risco</h2>
              <p className="mt-1 text-[11px] text-[#667085]">
                Snapshot da base — independente do período histórico abaixo. Sem score não é baixo risco.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                href="/trabalho"
                className="inline-flex h-8 items-center gap-1 rounded-lg border border-[#E4E7EC] bg-[#F8F9FA] px-2.5 text-[11px] font-semibold text-[#344054] hover:bg-white"
              >
                Central de Trabalho
                <ArrowRight className="h-3 w-3" />
              </Link>
              <Link
                href="/alunos?tab=dados_insuficientes"
                className="inline-flex h-8 items-center gap-1 rounded-lg border border-[#E4E7EC] bg-[#F8F9FA] px-2.5 text-[11px] font-semibold text-[#344054] hover:bg-white"
              >
                Sem score / cobertura
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
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
        </section>

        {historyQuery.isError && (
          <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5">
            <p className="text-[13px] font-semibold text-[#B42318]">
              Não foi possível carregar o histórico de risco.
            </p>
            <button type="button" onClick={refresh} className="mt-3 text-[12px] font-semibold text-[#B42318] underline">
              Tentar novamente
            </button>
          </div>
        )}

        {historyQuery.isLoading && historyPage === 1 ? (
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
                  hint={
                    "Sem anterior: " +
                    String(counts?.no_comparable_history ?? 0) +
                    " · modelo mudou: " +
                    String(counts?.model_changed ?? 0)
                  }
                  icon={<Users className="h-4 w-4" />}
                />
              </section>

              {data.temporal_data_truncated ? (
                <p className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] p-3 text-[12px] text-[#B54708]">
                  Série temporal limitada aos registros mais recentes; totais podem estar parciais.
                </p>
              ) : null}

              <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]">
                <div className="rounded-[10px] border border-[#E4E7EC] bg-white p-5">
                  <div className="mb-4">
                    <h2 className="text-[14px] font-semibold text-[#101828]">Evolução dos scores</h2>
                    <p className="mt-1 text-[11px] text-[#667085]">Média semanal por versão do modelo</p>
                  </div>
                  <ScoreTimeline data={data.timeline} />
                </div>
                <div className="rounded-[10px] border border-[#E4E7EC] bg-white p-5">
                  <div className="mb-4">
                    <h2 className="text-[14px] font-semibold text-[#101828]">Distribuição histórica</h2>
                    <p className="mt-1 text-[11px] text-[#667085]">Avaliação representativa por aluno/semana</p>
                  </div>
                  <DistributionTimeline data={data.timeline} />
                </div>
              </section>

              <section className="overflow-hidden rounded-[10px] border border-[#E4E7EC] bg-white">
                <div className="border-b border-[#E4E7EC] p-5">
                  <h2 className="text-[14px] font-semibold text-[#101828]">Movimentações de risco</h2>
                  <p className="mt-1 text-[11px] text-[#667085]">
                    Comparação entre avaliações. Delta só é legítimo quando a comparabilidade permite.
                  </p>
                </div>
                {movements.length === 0 ? (
                  <div className="p-10 text-center text-[13px] text-[#667085]">
                    {movementFilter
                      ? "Nenhuma movimentação com este filtro no período."
                      : "Nenhuma movimentação no período. Ausência de histórico ≠ estabilidade."}
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[1100px] text-left">
                      <thead className="bg-[#F8F9FA] text-[10px] font-semibold uppercase text-[#667085]">
                        <tr>
                          <th className="px-5 py-3">Aluno</th>
                          <th className="px-3 py-3">Anterior</th>
                          <th className="px-3 py-3">Atual</th>
                          <th className="px-3 py-3">Variação</th>
                          <th className="px-3 py-3">Movimento</th>
                          <th className="px-3 py-3">Comparabilidade</th>
                          <th className="px-3 py-3">Modelo</th>
                          <th className="px-5 py-3">Última avaliação</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#EAECF0]">
                        {movements.map((m) => (
                          <tr key={m.student_id} className="hover:bg-[#F8F9FA]">
                            <td className="px-5 py-3.5">
                              <button
                                type="button"
                                onClick={() => setSelectedStudentId(m.student_id)}
                                className="text-left text-[12px] font-semibold text-[#266DF0] hover:underline"
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
                              {m.delta == null
                                ? "—"
                                : (m.delta > 0 ? "+" : "") + scoreLabel(m.delta)}
                            </td>
                            <td className="px-3 py-3.5">
                              <span
                                className={cn(
                                  "inline-flex rounded-full px-2 py-1 text-[10px] font-medium",
                                  movementTone(m.change_type)
                                )}
                              >
                                {CHANGE_LABEL[m.change_type]}
                              </span>
                              {m.classification_changed ? (
                                <p className="mt-1 text-[10px] text-[#667085]">Nível mudou</p>
                              ) : null}
                            </td>
                            <td className="px-3 py-3.5">
                              <ComparabilityBadge change={m.change_type} />
                              {m.delta == null &&
                              (m.change_type === "mudanca_modelo" ||
                                m.change_type === "sem_historico_comparavel") ? (
                                <p className="mt-1 text-[10px] text-[#98A2B3]">Delta omitido</p>
                              ) : null}
                            </td>
                            <td className="px-3 py-3.5">
                              <ModelVersionCell
                                current={m.model_version}
                                previous={m.previous_model_version}
                              />
                              {m.score_semantics_version ? (
                                <p className="mt-0.5 text-[10px] text-[#98A2B3]">
                                  {m.score_semantics_version}
                                </p>
                              ) : null}
                            </td>
                            <td className="px-5 py-3.5 text-[11px] text-[#667085]">
                              {dateTimeLabel(m.current_evaluated_at)}
                              <Link
                                href={"/alunos/" + m.student_id}
                                className="mt-1 block text-[10px] font-semibold text-[#266DF0]"
                              >
                                Ficha
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E4E7EC] px-5 py-3">
                  <p className="text-[11px] text-[#667085]">
                    Exibindo {movements.length.toLocaleString("pt-BR")} movimentações
                    {movementFilter ? " (filtradas)" : ""}
                    {data?.movements_truncated ? " · página truncada pela API" : ""}
                  </p>
                  {canLoadMore ? (
                    <button
                      type="button"
                      disabled={historyQuery.isFetching}
                      onClick={() => setHistoryPage((p) => p + 1)}
                      className="inline-flex h-9 items-center rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-semibold text-[#344054] hover:bg-[#F8F9FA] disabled:opacity-60"
                    >
                      {historyQuery.isFetching ? "Carregando…" : "Carregar mais avaliações"}
                    </button>
                  ) : null}
                </div>
              </section>

              {selectedStudentId ? (
                <section className="rounded-xl border border-[#B2CCFF] bg-white p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-[14px] font-semibold text-[#101828]">Trajetória do aluno</h2>
                      <p className="mt-1 text-[11px] text-[#667085]">
                        {selectedHistoryQuery.data?.student.name || "Carregando…"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedStudentId(null)}
                      className="text-[11px] text-[#667085]"
                    >
                      Fechar
                    </button>
                  </div>
                  {selectedHistoryQuery.isLoading ? <Skeleton className="mt-4 h-20 rounded-lg" /> : null}
                  {selectedHistoryQuery.isError ? (
                    <p className="mt-4 text-[12px] text-[#B42318]">Falha ao carregar trajetória.</p>
                  ) : null}
                  {selectedHistoryQuery.data ? (
                    <>
                      <StudentAssessmentTimeline assessments={selectedHistoryQuery.data.assessments} />
                      <div className="mt-4 space-y-2">
                        {selectedHistoryQuery.data.assessments.map((a) => (
                          <div key={a.id} className="rounded-lg border border-[#E4E7EC] p-3">
                            <div className="flex justify-between gap-2">
                              <span className="text-[12px] font-semibold">
                                Score {scoreLabel(a.score)}
                              </span>
                              <RiskBadge level={a.risk_level} />
                            </div>
                            <p className="mt-1 text-[10px] text-[#667085]">
                              {dateTimeLabel(a.evaluated_at)}
                            </p>
                            <AssessmentModelLine a={a} />
                          </div>
                        ))}
                      </div>
                    </>
                  ) : null}
                </section>
              ) : null}
            </>
          )
        )}

        <details className="group rounded-[10px] border border-[#E4E7EC] bg-white open:shadow-sm">
          <summary className="cursor-pointer list-none px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-[14px] font-semibold text-[#101828]">
                  Analytics de intervenções
                  <span className="ml-2 text-[11px] font-medium text-[#98A2B3]">(secundário)</span>
                </h2>
                <p className="mt-1 text-[11px] text-[#667085]">
                  Métricas de retenção no período — não substituem a evolução de risco acima.
                </p>
              </div>
              <span className="text-[11px] font-semibold text-[#266DF0] group-open:hidden">Expandir</span>
              <span className="hidden text-[11px] font-semibold text-[#667085] group-open:inline">Recolher</span>
            </div>
          </summary>
          <div className="border-t border-[#E4E7EC] px-5 pb-5 pt-4">
            <RetentionAnalyticsPanel days={Number(period)} />
          </div>
        </details>
      </main>
    </>
  );
}

export function MonitoramentoPageView() {
  return (
    <Suspense
      fallback={
        <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 py-10">
          <div className="h-8 w-48 animate-pulse rounded bg-[#F2F4F7]" />
          <div className="h-40 animate-pulse rounded-xl bg-[#F2F4F7]" />
        </main>
      }
    >
      <MonitoramentoPageInner />
    </Suspense>
  );
}
