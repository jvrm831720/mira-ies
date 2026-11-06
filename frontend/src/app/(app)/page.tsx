"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  RefreshCw,
  Search,
  Upload,
  Users,
  TriangleAlert,
  UserRoundX,
  ClipboardList,
  MessageSquareHeart,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { CriticalList } from "@/components/risk/critical-list";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function CommandCenterPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const workSummary = useQuery({
    queryKey: ["retention-work-summary"],
    queryFn: () => api.retentionWorkSummary(),
    retry: false,
  });
  const critical = useQuery({ queryKey: ["risk-critical"], queryFn: () => api.riskCritical(8) });
  const activity = useQuery({
    queryKey: ["dashboard-recent-activity"],
    queryFn: () => api.retentionLogs({ limit: 5 }),
    retry: false,
  });
  const students = useQuery({
    queryKey: ["students-home"],
    queryFn: () => api.students({ limit: 80 }),
    retry: false,
  });

  const risk = summary.data?.summary;
  const riskBreakdownAvailable = Boolean(
    risk &&
      [risk.baixo, risk.medio, risk.critico, risk.sem_score].every(
        (count) => typeof count === "number" && Number.isFinite(count) && count >= 0
      )
  );
  const calculatedTotal =
    riskBreakdownAvailable && risk
      ? risk.baixo + risk.medio + risk.critico + risk.sem_score
      : null;
  const totalStudents =
    typeof summary.data?.total_students === "number" &&
    Number.isFinite(summary.data.total_students) &&
    summary.data.total_students >= 0
      ? summary.data.total_students
      : calculatedTotal;
  const scoredStudents =
    typeof summary.data?.total_scored === "number" &&
    Number.isFinite(summary.data.total_scored) &&
    summary.data.total_scored >= 0
      ? summary.data.total_scored
      : riskBreakdownAvailable && risk
        ? risk.baixo + risk.medio + risk.critico
        : null;
  const riskSegments =
    riskBreakdownAvailable && risk
      ? [
          { label: "Crítico", count: risk.critico, color: "bg-[#F04438]", text: "text-[#B42318]" },
          { label: "Médio", count: risk.medio, color: "bg-[#FDB022]", text: "text-[#B54708]" },
          { label: "Baixo", count: risk.baixo, color: "bg-[#12B76A]", text: "text-[#027A48]" },
          {
            label: "Sem score",
            count: risk.sem_score,
            color: "bg-[#D0D5DD]",
            text: "text-[#667085]",
          },
        ]
      : [];
  const riskTotal = riskSegments.reduce((sum, segment) => sum + segment.count, 0);
  const totalStudentsFieldValid =
    summary.data?.total_students == null ||
    (typeof summary.data.total_students === "number" &&
      Number.isFinite(summary.data.total_students) &&
      summary.data.total_students >= 0);
  const scoredStudentsFieldValid =
    summary.data?.total_scored == null ||
    (typeof summary.data.total_scored === "number" &&
      Number.isFinite(summary.data.total_scored) &&
      summary.data.total_scored >= 0);
  const riskDataConsistent = Boolean(
    riskBreakdownAvailable &&
      risk &&
      totalStudentsFieldValid &&
      scoredStudentsFieldValid &&
      totalStudents != null &&
      riskTotal === totalStudents &&
      (summary.data?.total_scored == null ||
        summary.data.total_scored === risk.baixo + risk.medio + risk.critico)
  );
  const operationalGeneratedAt = workSummary.data?.generated_at
    ? new Date(workSummary.data.generated_at)
    : null;
  const operationalGeneratedAtLabel =
    operationalGeneratedAt && !Number.isNaN(operationalGeneratedAt.getTime())
      ? new Intl.DateTimeFormat("pt-BR", {
          dateStyle: "medium",
          timeStyle: "short",
          timeZone: "America/Sao_Paulo",
        }).format(operationalGeneratedAt)
      : null;
  const criticalCount = riskDataConsistent && risk ? risk.critico : null;
  const unscoredCount = riskDataConsistent && risk ? risk.sem_score : null;
  const isEmpty = !summary.isLoading && !summary.isError && totalStudents === 0;

  const searchHits = useMemo(() => {
    const term = q.trim().toLocaleLowerCase("pt-BR");
    if (term.length < 2) return [];
    return (students.data?.students ?? [])
      .filter(
        (student) =>
          student.nome?.toLocaleLowerCase("pt-BR").includes(term) ||
          student.matricula?.toLocaleLowerCase("pt-BR").includes(term) ||
          student.curso?.toLocaleLowerCase("pt-BR").includes(term)
      )
      .slice(0, 5);
  }, [q, students.data]);

  function onSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const term = q.trim();
    if (!term) return;
    if (searchHits.length === 1) {
      setSelectedId(searchHits[0].id);
      setQ("");
      return;
    }
    router.push(`/alunos?q=${encodeURIComponent(term)}`);
  }

  async function refreshDashboard() {
    await Promise.all([
      summary.refetch(),
      workSummary.refetch(),
      critical.refetch(),
      activity.refetch(),
      students.refetch(),
    ]);
  }
  const isRefreshing =
    summary.isFetching ||
    workSummary.isFetching ||
    critical.isFetching ||
    activity.isFetching ||
    students.isFetching;

  return (
    <>
      <Header title="Visão geral" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-3 border-b border-[#E4E7EC] pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-[22px] font-semibold tracking-[-0.03em] text-[#111827] sm:text-[24px]">
              Visão geral
            </h1>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">
              Estado operacional da base e prioridades de acompanhamento.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-[12px] text-[#667085]">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                summary.isError ? "bg-[#F04438]" : summary.isLoading ? "bg-[#FDB022]" : "bg-[#12B76A]"
              )}
            />
            {summary.isError
              ? "Dados indisponíveis"
              : summary.isLoading
                ? "Consultando base"
                : "Resumo atualizado"}
          </div>
        </section>

        <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <form onSubmit={onSearchSubmit} className="relative w-full sm:max-w-[420px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#98A2B3]" />
            <input
              aria-label="Buscar aluno por nome, matrícula ou curso"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Buscar aluno"
              className="h-10 w-full rounded-lg border border-[#E5E7EB] bg-white pl-10 pr-3 text-[13px] text-[#111827] outline-none placeholder:text-[#98A2B3] focus:border-[#266DF0] focus:ring-2 focus:ring-[#266DF0]/15"
            />
            {searchHits.length > 0 && (
              <ul className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-lg border border-[#E5E7EB] bg-[#F8F9FA] shadow-lg">
                {searchHits.map((student) => (
                  <li key={student.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-white"
                      onClick={() => {
                        setSelectedId(student.id);
                        setQ("");
                      }}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium text-[#111827]">
                          {student.nome}
                        </span>
                        <span className="mt-0.5 block truncate text-[11px] text-[#667085]">
                          {student.matricula || "Sem matrícula"}
                          {student.curso ? ` · ${student.curso}` : ""}
                        </span>
                      </span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-[#98A2B3]" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </form>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void refreshDashboard()}
              disabled={isRefreshing}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#111827] transition hover:bg-[#F8F9FA] disabled:opacity-60"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
              Atualizar
            </button>
            <Link
              href="/importar"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#232529] px-4 text-[13px] font-medium text-white transition hover:bg-[#101112]"
            >
              <Upload className="h-3.5 w-3.5" />
              Importar
            </Link>
          </div>
        </section>

        {summary.isError ? (
          <section
            role="alert"
            className="flex flex-col gap-3 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-[#B42318]" />
              <div>
                <p className="text-sm font-semibold text-[#111827]">Não foi possível carregar os dados.</p>
                <p className="mt-1 text-sm text-[#667085]">Tente atualizar a página em instantes.</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void summary.refetch()}
              className="self-start text-sm font-semibold text-[#B42318] underline underline-offset-4 sm:self-auto"
            >
              Tentar novamente
            </button>
          </section>
        ) : (
          <section aria-label="Indicadores principais">
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <h2 className="text-[15px] font-semibold tracking-[-0.02em] text-[#111827]">
                  Indicadores principais
                </h2>
                <p className="mt-0.5 text-[12px] text-[#667085]">
                  Resumo da base e da operação de retenção.
                </p>
              </div>
              {!summary.isLoading && !summary.isError && (
                <span className="hidden text-[12px] text-[#98A2B3] sm:inline">
                  {scoredStudents?.toLocaleString("pt-BR") ?? "—"} com score
                </span>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Alunos na base"
                value={summary.isLoading ? "—" : (totalStudents?.toLocaleString("pt-BR") ?? "—")}
                hint={
                  summary.isLoading
                    ? "Carregando dados"
                    : totalStudents == null
                      ? "Total indisponível"
                      : "Total de alunos cadastrados"
                }
                icon={<Users className="h-4 w-4" />}
                tone="neutral"
                href="/alunos"
              />
              <MetricCard
                label="Precisam de atenção"
                value={summary.isLoading ? "—" : (criticalCount?.toLocaleString("pt-BR") ?? "—")}
                hint={
                  summary.isLoading
                    ? "Carregando dados"
                    : criticalCount == null
                      ? "Classificação indisponível"
                      : "Alunos em risco crítico"
                }
                icon={<TriangleAlert className="h-4 w-4" />}
                tone="coral"
                href="/alunos?risk=critico"
              />
              <MetricCard
                label="Intervenções pendentes"
                value={
                  workSummary.isLoading || workSummary.isError
                    ? "—"
                    : (workSummary.data?.pending?.toLocaleString("pt-BR") ?? "—")
                }
                hint={
                  workSummary.isError
                    ? "Indicador indisponível"
                    : "Decisões planejadas sem conclusão"
                }
                icon={<ClipboardList className="h-4 w-4" />}
                tone="indigo"
                href="/trabalho"
              />
              <MetricCard
                label="Atrasadas (>48h)"
                value={
                  workSummary.isLoading || workSummary.isError
                    ? "—"
                    : (workSummary.data?.overdue_48h?.toLocaleString("pt-BR") ?? "—")
                }
                hint={
                  workSummary.isError
                    ? "Indicador indisponível"
                    : typeof workSummary.data?.overdue_policy_hours === "number" &&
                        workSummary.data.overdue_policy_hours !== 48
                      ? "A contagem usa >48h; política configurada: " +
                        workSummary.data.overdue_policy_hours +
                        "h"
                      : workSummary.data?.overdue_policy_hours === 48
                        ? "Contagem conforme política de 48h"
                        : "Política operacional não informada"
                }
                icon={<UserRoundX className="h-4 w-4" />}
                tone="amber"
                href="/trabalho"
              />
            </div>

            {!summary.isLoading && !summary.isError && riskDataConsistent && risk && (
              <section
                className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]"
                aria-label="Distribuição de risco e qualidade da base"
              >
                <article className="rounded-xl border border-[#E5E7EB] bg-white p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="text-[13px] font-semibold text-[#111827]">Distribuição de risco</h3>
                      <p className="mt-1 text-[12px] text-[#667085]">
                        Classificação apenas com score. Sem score permanece separado.
                      </p>
                    </div>
                    <span className="rounded-full border border-[#E5E7EB] px-2.5 py-1 text-[11px] font-medium text-[#667085]">
                      {scoredStudents?.toLocaleString("pt-BR") ?? "—"} com score
                    </span>
                  </div>
                  <div
                    className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-[#F8F9FA]"
                    role="img"
                    aria-label={
                      riskTotal > 0
                        ? riskSegments.map((s) => s.label + ": " + s.count).join(", ")
                        : "Sem distribuição disponível"
                    }
                  >
                    {riskSegments
                      .filter((segment) => segment.count > 0 && riskTotal > 0)
                      .map((segment) => (
                        <div
                          key={segment.label}
                          className={segment.color + " h-full"}
                          style={{ width: (segment.count / riskTotal) * 100 + "%" }}
                          title={segment.label + ": " + segment.count}
                        />
                      ))}
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
                    {riskSegments.map((segment) => (
                      <div key={segment.label} className="min-w-0">
                        <div className="flex items-center gap-2 text-[11px] text-[#667085]">
                          <span className={"h-2 w-2 shrink-0 rounded-full " + segment.color} />
                          {segment.label}
                        </div>
                        <p className={"mt-1 text-xl font-semibold tabular-nums " + segment.text}>
                          {segment.count.toLocaleString("pt-BR")}
                        </p>
                        <p className="text-[11px] text-[#98A2B3]">
                          {riskTotal > 0
                            ? ((segment.count / riskTotal) * 100).toLocaleString("pt-BR", {
                                maximumFractionDigits: 1,
                              }) + "% da distribuição"
                            : "Sem dados"}
                        </p>
                      </div>
                    ))}
                  </div>
                </article>
                <article className="rounded-xl border border-[#E5E7EB] bg-white p-4 sm:p-5">
                  <h3 className="text-[13px] font-semibold text-[#111827]">Cobertura da análise</h3>
                  <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">
                    Alunos sem score não entram como baixo risco e exigem revisão de dados.
                  </p>
                  <div className="mt-5 flex items-end justify-between gap-3">
                    <div>
                      <p className="text-[28px] font-semibold tracking-[-0.04em] tabular-nums text-[#111827]">
                        {unscoredCount?.toLocaleString("pt-BR") ?? "—"}
                      </p>
                      <p className="mt-1 text-[11px] text-[#667085]">Sem score</p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-semibold tabular-nums text-[#111827]">
                        {totalStudents != null && totalStudents > 0 && unscoredCount != null
                          ? ((unscoredCount / totalStudents) * 100).toLocaleString("pt-BR", {
                              maximumFractionDigits: 1,
                            }) + "%"
                          : "—"}
                      </p>
                      <p className="mt-1 text-[11px] text-[#667085]">da base total</p>
                    </div>
                  </div>
                  <Link
                    href="/alunos"
                    className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-semibold text-[#266DF0] hover:text-[#1F5DD1]"
                  >
                    Revisar alunos sem score
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                  {operationalGeneratedAtLabel && (
                    <p className="mt-4 border-t border-[#E5E7EB] pt-3 text-[11px] text-[#98A2B3]">
                      Resumo operacional gerado em {operationalGeneratedAtLabel}
                    </p>
                  )}
                </article>
              </section>
            )}
            {!summary.isLoading && !summary.isError && !riskDataConsistent && (
              <p
                role="status"
                className="mt-4 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] px-4 py-3 text-[13px] text-[#B54708]"
              >
                A distribuição de risco e a cobertura não estão disponíveis porque os dados da API
                estão incompletos ou inconsistentes. Os valores não foram tratados como zero.
              </p>
            )}
          </section>
        )}

        {isEmpty ? (
          <section className="rounded-xl border border-[#E5E7EB] bg-white px-5 py-10 text-center sm:py-14">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[#F8F9FA] text-[#266DF0]">
              <Upload className="h-5 w-5" />
            </span>
            <h2 className="mt-4 text-[16px] font-semibold tracking-[-0.02em] text-[#111827]">
              Vamos começar pela sua base de alunos
            </h2>
            <p className="mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-[#667085]">
              Envie uma planilha para ver os alunos e identificar quem precisa de atenção.
            </p>
            <Link
              href="/importar"
              className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-[#232529] px-4 text-[13px] font-medium text-white hover:bg-[#101112]"
            >
              <Upload className="h-3.5 w-3.5" />
              Importar alunos
            </Link>
          </section>
        ) : (
          !summary.isError && (
            <section
              className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]"
              aria-label="Prioridade e atividade"
            >
              <CriticalList
                showExplanations={hasNavigationPermission(me.data, "students.sensitive.view")}
                students={critical.data?.students.map(item => ({
          ...item, ...(students.data?.students.find(row => row.id === item.id) || {}),
        }))}
                loading={critical.isLoading}
                onSelect={(id) => setSelectedId(id)}
              />
              <RecentActivity
                logs={activity.data?.logs}
                loading={activity.isLoading}
                error={activity.isError}
                onRetry={() => void activity.refetch()}
              />
            </section>
          )
        )}

        {!isEmpty && !summary.isError && (
          <section className="grid gap-3 sm:grid-cols-2" aria-label="Atalhos operacionais">
            <Link
              href="/trabalho"
              className="group flex items-center gap-3 rounded-xl border border-[#E5E7EB] bg-white p-4 transition hover:border-[#CBD5E1] hover:shadow-sm"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#F8F9FA] text-[#667085]">
                <ClipboardList className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-semibold text-[#111827]">Central de trabalho</span>
                <span className="mt-0.5 block text-[12px] text-[#667085]">
                  Intervenções e acompanhamento.
                </span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-[#98A2B3] transition group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/retencao"
              className="group flex items-center gap-3 rounded-xl border border-[#E5E7EB] bg-white p-4 transition hover:border-[#CBD5E1] hover:shadow-sm"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#F8F9FA] text-[#667085]">
                <MessageSquareHeart className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-semibold text-[#111827]">Intervenções</span>
                <span className="mt-0.5 block text-[12px] text-[#667085]">Régua de retenção e fluxos.</span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-[#98A2B3] transition group-hover:translate-x-0.5" />
            </Link>
          </section>
        )}

        {!isEmpty && !summary.isError && (
          <div className="flex items-center gap-2 border-t border-[#E5E7EB] pt-4 text-[12px] text-[#98A2B3]">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[#027A48]" />
            Indicadores refletem apenas dados retornados pela API; ausência não é tratada como zero.
          </div>
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
  href,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone: "neutral" | "coral" | "indigo" | "amber";
  href?: string;
}) {
  const tones = {
    neutral: "text-[#667085]",
    coral: "text-[#B42318]",
    indigo: "text-[#266DF0]",
    amber: "text-[#B54708]",
  };
  const body = (
    <>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#98A2B3]">{label}</p>
        <span className={cn("shrink-0", tones[tone])}>{icon}</span>
      </div>
      <p className="mt-4 text-[28px] font-semibold leading-none tracking-[-0.04em] tabular-nums text-[#111827]">
        {value}
      </p>
      <p className="mt-2 text-[11px] leading-snug text-[#667085]">{hint}</p>
    </>
  );
  const cls =
    "block rounded-xl border border-[#E5E7EB] bg-white p-4 transition hover:border-[#D0D5DD] hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#266DF0]";
  if (href) {
    return (
      <Link href={href} data-mira-card="true" className={cls}>
        {body}
      </Link>
    );
  }
  return (
    <article data-mira-card="true" className={cls}>
      {body}
    </article>
  );
}
