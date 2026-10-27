"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CheckCircle2, RefreshCw, Search, Upload, Users, TriangleAlert, UserRoundX, ClipboardList, MessageSquareHeart } from "lucide-react";
import { Header } from "@/components/layout/header";
import { CriticalList } from "@/components/risk/critical-list";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";

export default function CommandCenterPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const workSummary = useQuery({ queryKey: ["retention-work-summary"], queryFn: () => api.retentionWorkSummary(), retry: false });
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
  const scoredStudents = summary.data?.total_scored ?? (risk ? risk.baixo + risk.medio + risk.critico : 0);
  const calculatedTotal = risk ? risk.baixo + risk.medio + risk.critico + risk.sem_score : 0;
  const totalStudents = summary.data?.total_students ?? calculatedTotal;
  const riskSegments = risk ? [
    { label: "Crítico", count: risk.critico, color: "bg-rose-500", text: "text-rose-700" },
    { label: "Médio", count: risk.medio, color: "bg-amber-400", text: "text-amber-700" },
    { label: "Baixo", count: risk.baixo, color: "bg-emerald-500", text: "text-emerald-700" },
    { label: "Sem score", count: risk.sem_score, color: "bg-neutral-300", text: "text-neutral-600" },
  ] : [];
  const riskTotal = riskSegments.reduce((sum, segment) => sum + segment.count, 0);
  const operationalGeneratedAt = workSummary.data?.generated_at ? new Date(workSummary.data.generated_at) : null;
  const operationalGeneratedAtLabel = operationalGeneratedAt && !Number.isNaN(operationalGeneratedAt.getTime())
    ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(operationalGeneratedAt)
    : null;
  const criticalCount = risk?.critico ?? 0;
  const unscoredCount = risk?.sem_score ?? 0;
  const isEmpty = !summary.isLoading && !summary.isError && totalStudents === 0;

  const searchHits = useMemo(() => {
    const term = q.trim().toLocaleLowerCase("pt-BR");
    if (term.length < 2) return [];
    return (students.data?.students ?? []).filter((student) =>
      student.nome?.toLocaleLowerCase("pt-BR").includes(term) ||
      student.matricula?.toLocaleLowerCase("pt-BR").includes(term) ||
      student.curso?.toLocaleLowerCase("pt-BR").includes(term)
    ).slice(0, 5);
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
    await Promise.all([summary.refetch(), workSummary.refetch(), critical.refetch(), activity.refetch(), students.refetch()]);
  }
  const isRefreshing = summary.isFetching || workSummary.isFetching || critical.isFetching || activity.isFetching || students.isFetching;

  return (
    <>
      <Header title="Visão geral" compact />
      <main className="mx-auto w-full max-w-[1440px] space-y-[var(--space-8)] px-4 pb-10 pt-5 md:px-8 md:pt-7 xl:px-10 mira-page">
        <section className="flex flex-col gap-4 border-b border-neutral-200/80 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand-indigo)]">Inteligência de permanência</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-neutral-950 sm:text-4xl">Visão geral</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-neutral-500">Entenda a distribuição de risco, identifique lacunas na base e priorize a próxima ação.</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-xs text-neutral-500">
            <span className={"h-2 w-2 rounded-full " + (summary.isError ? "bg-rose-500" : summary.isLoading ? "bg-amber-400" : "bg-emerald-500")} />
            {summary.isError ? "Dados indisponíveis" : summary.isLoading ? "Consultando base" : "Resumo carregado"}
          </div>
        </section>
        <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <form onSubmit={onSearchSubmit} className="relative w-full sm:max-w-[480px]">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <input
              aria-label="Buscar aluno por nome, matrícula ou curso"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Buscar aluno"
              className="h-12 w-full rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white pl-11 pr-4 text-sm text-[var(--text-primary)] shadow-sm outline-none transition placeholder:text-neutral-400 focus:border-[var(--brand-indigo)] focus:ring-4 focus:ring-[rgba(64,80,205,0.10)]"
            />
            {searchHits.length > 0 && (
              <ul className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-xl">
                {searchHits.map((student) => (
                  <li key={student.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-neutral-50"
                      onClick={() => { setSelectedId(student.id); setQ(""); }}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-neutral-900">{student.nome}</span>
                        <span className="mt-0.5 block truncate text-xs text-[var(--text-secondary)]">
                          {student.matricula || "Sem matrícula"}{student.curso ? ` · ${student.curso}` : ""}
                        </span>
                      </span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-neutral-400" />
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
              className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-4 text-sm font-semibold text-neutral-700 shadow-sm transition hover:border-neutral-300 hover:bg-neutral-50 disabled:opacity-60"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              Atualizar
            </button>
            <Link
              href="/importar"
              className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] bg-[var(--brand-midnight)] px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-neutral-800 hover:shadow-md"
            >
              <Upload className="h-3.5 w-3.5" />
              Importar alunos
            </Link>
          </div>
        </section>

        {summary.isError ? (
          <section role="alert" className="flex flex-col gap-3 rounded-2xl border border-red-200 bg-red-50 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
              <div>
                <p className="text-sm font-semibold text-red-900">Não foi possível carregar os dados.</p>
                <p className="mt-1 text-sm text-red-800/80">Tente atualizar a página em instantes.</p>
              </div>
            </div>
            <button type="button" onClick={() => void summary.refetch()} className="self-start text-sm font-semibold text-red-900 underline underline-offset-4 sm:self-auto">Tentar novamente</button>
          </section>
        ) : (
          <section aria-label="Resumo dos alunos">
            <div className="mb-4 flex items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold tracking-[-0.04em] text-neutral-950">Sua instituição, em resumo</h2>
                <p className="mt-1 text-sm text-neutral-500">Entenda a situação da base e escolha onde agir primeiro.</p>
              </div>
              {!summary.isLoading && !summary.isError && (
                <span className="hidden text-xs text-neutral-400 sm:inline">
                  {scoredStudents.toLocaleString("pt-BR")} com score
                </span>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Alunos na base"
                value={summary.isLoading ? "—" : totalStudents.toLocaleString("pt-BR")}
                hint={summary.isLoading ? "Carregando dados" : "Total de alunos cadastrados"}
                icon={<Users className="h-5 w-5" />}
                tone="neutral"
              />
              <MetricCard
                label="Precisam de atenção"
                value={summary.isLoading ? "—" : criticalCount.toLocaleString("pt-BR")}
                hint={summary.isLoading ? "Carregando dados" : "Alunos em risco crítico"}
                icon={<TriangleAlert className="h-5 w-5" />}
                tone="coral"
              />
              <MetricCard
                label="Intervenções pendentes"
                value={workSummary.isLoading || workSummary.isError ? "—" : workSummary.data?.pending?.toLocaleString("pt-BR") ?? "—"}
                hint={workSummary.isError ? "Indicador indisponível" : "Decisões planejadas sem conclusão"}
                icon={<ClipboardList className="h-5 w-5" />}
                tone="indigo"
              />
              <MetricCard
                label="Intervenções atrasadas"
                value={workSummary.isLoading || workSummary.isError ? "—" : workSummary.data?.overdue_48h?.toLocaleString("pt-BR") ?? "—"}
                hint={workSummary.isError ? "Indicador indisponível" : workSummary.data?.overdue_policy_hours ? "Regra operacional informada: " + workSummary.data.overdue_policy_hours + "h" : "Prazo operacional não informado"}
                icon={<UserRoundX className="h-5 w-5" />}
                tone="coral"
              />
            </div>
            {!summary.isLoading && !summary.isError && risk && (
              <section className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)]" aria-label="Distribuição de risco e qualidade da base">
                <article className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 sm:p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-neutral-900">Distribuição de risco</h3>
                      <p className="mt-1 text-xs text-neutral-500">A classificação considera apenas alunos com score. “Sem score” permanece como uma categoria separada.</p>
                    </div>
                    <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-600">{scoredStudents.toLocaleString("pt-BR")} com score</span>
                  </div>
                  <div className="mt-5 flex h-3 overflow-hidden rounded-full bg-neutral-100" role="img" aria-label={riskTotal > 0 ? riskSegments.map((segment) => segment.label + ": " + segment.count).join(", ") : "Sem distribuição disponível"}>
                    {riskSegments.filter((segment) => segment.count > 0 && riskTotal > 0).map((segment) => (
                      <div key={segment.label} className={segment.color + " h-full"} style={{ width: ((segment.count / riskTotal) * 100) + "%" }} title={segment.label + ": " + segment.count} />
                    ))}
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
                    {riskSegments.map((segment) => (
                      <div key={segment.label} className="min-w-0">
                        <div className="flex items-center gap-2 text-xs text-neutral-500"><span className={"h-2 w-2 shrink-0 rounded-full " + segment.color} />{segment.label}</div>
                        <p className={"mt-1 text-xl font-semibold tabular-nums " + segment.text}>{segment.count.toLocaleString("pt-BR")}</p>
                        <p className="text-[11px] text-neutral-400">{riskTotal > 0 ? ((segment.count / riskTotal) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "% dos registros com score" : "Sem dados para calcular"}</p>
                      </div>
                    ))}
                  </div>
                </article>
                <article className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 sm:p-6">
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-700"><UserRoundX className="h-4 w-4" /></span>
                    <div>
                      <h3 className="text-sm font-semibold text-neutral-900">Cobertura da análise</h3>
                      <p className="mt-1 text-xs leading-relaxed text-neutral-500">Alunos sem score não são classificados como baixo risco e precisam de revisão de dados ou processamento.</p>
                    </div>
                  </div>
                  <div className="mt-5 flex items-end justify-between gap-3">
                    <div><p className="text-3xl font-semibold tracking-[-0.05em] tabular-nums text-neutral-950">{unscoredCount.toLocaleString("pt-BR")}</p><p className="mt-1 text-xs text-neutral-500">Sem score</p></div>
                    <div className="text-right"><p className="text-lg font-semibold tabular-nums text-neutral-800">{totalStudents > 0 ? ((unscoredCount / totalStudents) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%" : "—"}</p><p className="mt-1 text-xs text-neutral-500">da base total</p></div>
                  </div>
                  <Link href="/alunos?risk=sem_score" className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--brand-indigo)] hover:text-[var(--brand-blue)]">Revisar alunos sem score <ArrowRight className="h-3.5 w-3.5" /></Link>
                  {operationalGeneratedAtLabel && <p className="mt-4 border-t border-neutral-100 pt-3 text-[11px] text-neutral-400">Resumo operacional gerado em {operationalGeneratedAtLabel}</p>}
                </article>
              </section>
            )}
          </section>
        )}

        {isEmpty ? (
          <section className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-card)] px-5 py-10 text-center sm:py-14">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[var(--brand-paper)] text-[var(--brand-indigo)]">
              <Upload className="h-5 w-5" />
            </span>
            <h2 className="mt-4 text-lg font-semibold tracking-[-0.03em] text-neutral-950">Vamos começar pela sua base de alunos</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-neutral-500">
              Envie uma planilha para ver os alunos e identificar quem precisa de atenção.
            </p>
            <Link href="/importar" className="mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--brand-midnight)] px-4 text-sm font-semibold text-white transition hover:bg-neutral-800">
              Importar alunos <ArrowRight className="h-4 w-4" />
            </Link>
          </section>
        ) : (
          <section className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.75fr)]" aria-label="Prioridades e atividade">
            <div className="min-w-0">
              <CriticalList students={critical.data?.students} loading={critical.isLoading} onSelect={setSelectedId} />
              {critical.isError && (
                <p role="alert" className="mt-2 text-sm text-red-700">
                  Não foi possível carregar a lista. <button type="button" onClick={() => void critical.refetch()} className="font-semibold underline underline-offset-2">Tentar novamente</button>
                </p>
              )}
            </div>
            <div className="min-w-0">
              <RecentActivity logs={activity.data?.logs} loading={activity.isLoading} error={activity.isError} onRetry={() => void activity.refetch()} />
            </div>
          </section>
        )}

        {!summary.isError && (
          <section aria-label="Ações rápidas" className="grid gap-3 sm:grid-cols-2">
            <Link href="/retencao/logs" className="group flex items-center gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 transition duration-200 hover:-translate-y-0.5 hover:border-neutral-300 hover:shadow-md">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-neutral-100 text-neutral-700"><ClipboardList className="h-5 w-5" /></span>
              <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-neutral-900">Central de trabalho</span><span className="mt-1 block text-xs text-neutral-500">Revise os registros de intervenção e identifique o que exige acompanhamento.</span></span>
              <ArrowRight className="h-4 w-4 shrink-0 text-neutral-400 transition group-hover:translate-x-0.5" />
            </Link>
            <Link href="/retencao" className="group flex items-center gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 transition duration-200 hover:-translate-y-0.5 hover:border-neutral-300 hover:shadow-md">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#eef0ff] text-[var(--brand-indigo)]"><MessageSquareHeart className="h-5 w-5" /></span>
              <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-neutral-900">Intervenções</span><span className="mt-1 block text-xs text-neutral-500">Acesse a régua de retenção e os fluxos disponíveis para sua instituição.</span></span>
              <ArrowRight className="h-4 w-4 shrink-0 text-neutral-400 transition group-hover:translate-x-0.5" />
            </Link>
          </section>
        )}

        {!isEmpty && !summary.isError && (
          <div className="flex items-center gap-2 border-t border-neutral-200/80 pt-4 text-xs text-neutral-400">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
            Os indicadores ajudam a equipe a priorizar o acompanhamento dos alunos.
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
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone: "neutral" | "coral" | "indigo";
}) {
  const tones = {
    neutral: "bg-neutral-100 text-neutral-600",
    coral: "bg-[#fff0ed] text-[#d45f52]",
    indigo: "bg-[#eef0ff] text-[var(--brand-indigo)]",
  };
  return (
    <article data-mira-card="true" className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-white p-5 transition duration-200 hover:-translate-y-0.5 hover:border-neutral-300 hover:shadow-lg sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-neutral-500">{label}</p>
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${tones[tone]}`}>{icon}</span>
      </div>
      <p className="mt-5 text-3xl font-semibold leading-none tracking-[-0.055em] tabular-nums text-neutral-950">{value}</p>
      <p className="mt-2 text-xs text-neutral-400">{hint}</p>
    </article>
  );
}
