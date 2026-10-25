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
  const totalStudents = summary.data?.total_students ?? scoredStudents;
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
        <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <form onSubmit={onSearchSubmit} className="relative w-full sm:max-w-[480px]">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <input
              aria-label="Buscar aluno por nome, matrícula ou curso"
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Buscar aluno"
              className="h-11 w-full rounded-xl border border-neutral-200 bg-white pl-10 pr-4 text-sm text-neutral-900 outline-none transition placeholder:text-neutral-400 focus:border-[var(--brand-indigo)] focus:ring-4 focus:ring-[rgba(64,80,205,0.09)]"
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
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-neutral-200 bg-white px-3.5 text-sm font-medium text-neutral-700 transition hover:bg-neutral-50 disabled:opacity-60"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              Atualizar
            </button>
            <Link
              href="/importar"
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--brand-midnight)] px-4 text-sm font-semibold text-white transition hover:bg-neutral-800"
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
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold tracking-[-0.035em] text-neutral-950">Sua instituição, em resumo</h2>
                <p className="mt-1 text-sm text-neutral-500">Entenda a situação da base e escolha onde agir primeiro.</p>
              </div>
              {!summary.isLoading && (
                <span className="hidden text-xs text-neutral-400 sm:inline">
                  {scoredStudents.toLocaleString("pt-BR")} analisados
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
                label="Planejadas há +48h"
                value={workSummary.isLoading || workSummary.isError ? "—" : workSummary.data?.overdue_48h?.toLocaleString("pt-BR") ?? "—"}
                hint={workSummary.isError ? "Indicador indisponível" : "Sinal operacional com política provisória de 48h"}
                icon={<UserRoundX className="h-5 w-5" />}
                tone="coral"
              />
            </div>
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
            <Link href="/retencao/logs" className="group flex items-center gap-3 rounded-2xl border border-neutral-200 bg-white p-4 transition hover:border-neutral-300 hover:shadow-sm">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-neutral-100 text-neutral-700"><ClipboardList className="h-5 w-5" /></span>
              <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-neutral-900">Central de trabalho</span><span className="mt-1 block text-xs text-neutral-500">Revise os registros de intervenção e identifique o que exige acompanhamento.</span></span>
              <ArrowRight className="h-4 w-4 shrink-0 text-neutral-400 transition group-hover:translate-x-0.5" />
            </Link>
            <Link href="/retencao" className="group flex items-center gap-3 rounded-2xl border border-neutral-200 bg-white p-4 transition hover:border-neutral-300 hover:shadow-sm">
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
    <article className="rounded-2xl border border-neutral-200/80 bg-white p-5 transition duration-200 hover:border-neutral-300 hover:shadow-[0_8px_24px_rgba(20,20,30,0.045)] sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-neutral-500">{label}</p>
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${tones[tone]}`}>{icon}</span>
      </div>
      <p className="mt-5 text-3xl font-semibold leading-none tracking-[-0.055em] tabular-nums text-neutral-950">{value}</p>
      <p className="mt-2 text-xs text-neutral-400">{hint}</p>
    </article>
  );
}
