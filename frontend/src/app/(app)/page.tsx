"use client";
import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ArrowUpRight, Database, GraduationCap, Info, MessageSquareHeart, Plug, RefreshCw, Search, ShieldCheck, Sparkles, Upload, Users } from "lucide-react";
import { Header } from "@/components/layout/header";
import { KpiCards } from "@/components/risk/kpi-cards";
import { CriticalList } from "@/components/risk/critical-list";
import { RiskDistribution } from "@/components/risk/risk-distribution";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { OperationalOverview } from "@/components/dashboard/operational-overview";
import { StudentDrawer } from "@/components/students/student-drawer";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { copy } from "@/lib/copy";

const quickActions = [
  { href: "/importar", label: "Importar dados", icon: Upload },
  { href: "/alunos", label: "Explorar alunos", icon: Users },
  { href: "/retencao", label: "Régua de retenção", icon: MessageSquareHeart },
  { href: "/conectores", label: "Conectores", icon: Plug },
];

export default function CommandCenterPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const critical = useQuery({ queryKey: ["risk-critical"], queryFn: () => api.riskCritical(10) });
  const model = useQuery({ queryKey: ["model-info"], queryFn: () => api.modelInfo(), retry: false });
  const agents = useQuery({ queryKey: ["agents-status"], queryFn: () => api.agentsStatus(), retry: false });
  const activity = useQuery({ queryKey: ["dashboard-recent-activity"], queryFn: () => api.retentionLogs({ limit: 6 }), retry: false });
  const students = useQuery({ queryKey: ["students-home"], queryFn: () => api.students({ limit: 80 }), retry: false });

  const total = summary.data?.total_scored ?? (summary.data?.summary
    ? summary.data.summary.baixo + summary.data.summary.medio + summary.data.summary.critico : 0);
  const allStudents = summary.data?.total_students ?? total;
  const criticalCount = summary.data?.summary.critico ?? 0;
  const priorityRate = total ? Math.round((criticalCount / total) * 100) : 0;
  const isEmpty = !summary.isLoading && !summary.isError && allStudents === 0;

  const searchHits = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (term.length < 2) return [];
    return (students.data?.students ?? []).filter((student) =>
      student.nome?.toLowerCase().includes(term) ||
      student.matricula?.toLowerCase().includes(term) ||
      student.curso?.toLowerCase().includes(term)
    ).slice(0, 6);
  }, [q, students.data]);

  function onSearchSubmit(event: FormEvent) {
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
    await Promise.all([summary.refetch(), critical.refetch(), model.refetch(), agents.refetch(), activity.refetch(), students.refetch()]);
  }
  const isRefreshing = summary.isFetching || critical.isFetching || model.isFetching || agents.isFetching || activity.isFetching || students.isFetching;

  return (
    <>
      <Header title="Visão geral" subtitle="Uma leitura clara dos riscos e das próximas ações da sua instituição." />
      <main className="mx-auto w-full max-w-[1600px] space-y-6 px-4 pb-12 pt-5 md:px-8 md:pt-7 xl:px-10">
        <section className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <form onSubmit={onSearchSubmit} className="relative w-full xl:max-w-[520px]">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-[17px] w-[17px] -translate-y-1/2 text-[var(--brand-indigo)]" />
            <input aria-label="Buscar aluno" value={q} onChange={(event) => setQ(event.target.value)}
              placeholder="Buscar por nome, matrícula ou curso..."
              className="h-12 w-full rounded-2xl border border-black/[0.08] bg-white pl-11 pr-4 text-[13px] text-neutral-900 shadow-[0_8px_28px_rgba(31,33,42,0.035)] outline-none transition placeholder:text-neutral-400 focus:border-[var(--brand-indigo)] focus:ring-4 focus:ring-[rgba(64,80,205,0.1)]" />
            {searchHits.length > 0 && (
              <ul className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-xl">
                {searchHits.map((student) => (
                  <li key={student.id}>
                    <button type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm transition hover:bg-neutral-50"
                      onClick={() => { setSelectedId(student.id); setQ(""); }}>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-neutral-900">{student.nome}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-neutral-500">{student.matricula || "Sem matrícula"}{student.curso ? ` · ${student.curso}` : ""}</span>
                      </span>
                      <span className="shrink-0 rounded-full bg-[var(--brand-paper)] px-2.5 py-1 text-[10px] font-semibold capitalize text-neutral-600">{student.risk_level || "Sem score"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </form>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => void refreshDashboard()} disabled={isRefreshing}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-black/[0.08] bg-white px-3.5 text-xs font-semibold text-neutral-700 transition hover:bg-neutral-50 disabled:opacity-60">
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} /> Atualizar dados
            </button>
            <Link href="/importar" className="inline-flex h-10 items-center gap-2 rounded-xl bg-neutral-950 px-4 text-xs font-semibold text-white transition hover:bg-neutral-800">
              <Upload className="h-3.5 w-3.5" /> Importar base
            </Link>
          </div>
        </section>

        <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" aria-label="Ações rápidas">
          {quickActions.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className="group flex items-center gap-3 rounded-2xl border border-black/[0.07] bg-white px-3.5 py-3 transition duration-200 hover:-translate-y-0.5 hover:border-[rgba(64,80,205,0.25)] hover:shadow-[0_12px_28px_rgba(31,33,42,0.06)]">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[rgba(64,80,205,0.09)] text-[var(--brand-indigo)] transition group-hover:bg-[var(--brand-indigo)] group-hover:text-white"><Icon className="h-[17px] w-[17px]" /></span>
              <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-neutral-800">{label}</span>
              <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-neutral-300 transition group-hover:text-[var(--brand-indigo)]" />
            </Link>
          ))}
        </section>

        <section className="relative isolate overflow-hidden rounded-[26px] bg-[var(--brand-midnight)] px-5 py-6 text-white shadow-[0_18px_48px_rgba(23,25,29,0.13)] sm:px-7 sm:py-7 lg:px-9">
          <div className="pointer-events-none absolute -right-24 -top-32 h-80 w-80 rounded-full border-[32px] border-[rgba(64,80,205,0.25)]" />
          <div className="pointer-events-none absolute -bottom-36 right-[18%] h-64 w-64 rounded-full border border-white/[0.07]" />
          <div className="relative grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-white/65">
                <Sparkles className="h-3.5 w-3.5 text-[#9da6ff]" /> Mira · inteligência para permanência
              </div>
              <h2 className="mt-4 max-w-2xl text-[25px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-[31px]">Transforme sinais de risco em ações de permanência.</h2>
              <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-white/60">
                {summary.isError ? "Não foi possível carregar os indicadores agora. Atualize os dados para consultar a situação da sua base."
                  : isEmpty ? "Sua instituição ainda não tem uma base analisada. Importe os dados para começar a identificar quem precisa de apoio."
                    : `${allStudents.toLocaleString("pt-BR")} alunos na base · ${total.toLocaleString("pt-BR")} com score de risco · ${criticalCount.toLocaleString("pt-BR")} em faixa crítica.`}
              </p>
              <div className="mt-5 flex flex-wrap gap-2.5">
                <Link href={isEmpty ? "/importar" : "/alunos?risk=critico"} className="inline-flex h-10 items-center gap-2 rounded-xl bg-white px-4 text-xs font-semibold text-[var(--brand-midnight)] transition hover:bg-white/90">
                  {isEmpty ? "Importar primeira base" : "Revisar alunos críticos"} <ArrowRight className="h-3.5 w-3.5" />
                </Link>
                <Link href="/retencao" className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-4 text-xs font-semibold text-white transition hover:bg-white/10">Abrir retenção</Link>
              </div>
            </div>
            <div className="relative flex min-w-[205px] items-center gap-4 rounded-2xl border border-white/10 bg-white/[0.055] px-5 py-4 lg:min-w-[230px]">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[rgba(244,119,105,0.14)] text-[#ff9a8d]"><AlertTriangle className="h-5 w-5" /></span>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/45">Risco crítico</p>
                <p className="mt-1 text-[31px] font-semibold leading-none tracking-[-0.05em] tabular-nums">{summary.isLoading ? "—" : summary.isError ? "!" : criticalCount.toLocaleString("pt-BR")}</p>
                <p className="mt-1.5 text-[11px] text-white/55">{summary.isError ? "Indicador indisponível" : total ? `${priorityRate}% dos alunos pontuados` : "Aguardando primeira análise"}</p>
              </div>
            </div>
          </div>
        </section>

        <section aria-label="Indicadores de risco" className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div><p className="text-[10px] font-semibold uppercase tracking-[0.17em] text-neutral-400">Visão da base</p><h2 className="mt-1 text-[20px] font-semibold tracking-[-0.04em] text-neutral-950">Resumo de risco</h2></div>
            {!summary.isError && !summary.isLoading && <span className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 text-[10px] font-medium text-neutral-500"><Database className="h-3 w-3 text-[var(--brand-indigo)]" /> {allStudents.toLocaleString("pt-BR")} registros na base</span>}
          </div>
          {summary.isError ? (
            <Card className="border-red-200 bg-red-50 shadow-none"><CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" /><div><p className="text-sm font-semibold text-red-900">Não foi possível carregar os indicadores.</p><p className="mt-1 text-xs text-red-800/80">Verifique a conexão com a API e tente novamente.</p></div></div>
              <button type="button" onClick={() => void summary.refetch()} className="self-start text-xs font-semibold text-red-900 underline underline-offset-4 sm:self-auto">Tentar novamente</button>
            </CardContent></Card>
          ) : <KpiCards data={summary.data} loading={summary.isLoading} />}
        </section>

        {isEmpty && <section className="rounded-[22px] border border-dashed border-neutral-300 bg-white px-5 py-10 text-center">
          <GraduationCap className="mx-auto h-8 w-8 text-neutral-300" />
          <p className="mt-3 text-sm font-semibold text-neutral-900">Sua primeira análise começa aqui</p>
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-neutral-500">Importe uma planilha ou configure um conector para visualizar a distribuição de risco e priorizar o acompanhamento.</p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <Link href="/importar" className="inline-flex h-9 items-center gap-2 rounded-xl bg-neutral-950 px-3.5 text-xs font-semibold text-white hover:bg-neutral-800"><Upload className="h-3.5 w-3.5" /> Importar base</Link>
            <Link href="/conectores" className="inline-flex h-9 items-center gap-2 rounded-xl border border-neutral-200 bg-white px-3.5 text-xs font-semibold text-neutral-700 hover:bg-neutral-50"><Plug className="h-3.5 w-3.5" /> Ver conectores</Link>
          </div>
        </section>}

        <section className="grid gap-4 xl:grid-cols-12" aria-label="Análise e operação">
          <div className="min-w-0 xl:col-span-5">
            {summary.isError ? <Card className="h-full"><CardContent className="flex h-full min-h-[250px] flex-col items-center justify-center p-6 text-center"><Database className="h-7 w-7 text-neutral-300" /><p className="mt-3 text-sm font-semibold text-neutral-800">Panorama indisponível</p><p className="mt-1 max-w-xs text-xs text-neutral-500">A distribuição será exibida quando os dados puderem ser carregados.</p></CardContent></Card>
              : <RiskDistribution data={summary.data} loading={summary.isLoading} />}
          </div>
          <div className="min-w-0 xl:col-span-7"><OperationalOverview model={model.data} agents={agents.data} modelLoading={model.isLoading} agentsLoading={agents.isLoading} modelError={model.isError} agentsError={agents.isError} /></div>
        </section>

        <section className="grid gap-4 xl:grid-cols-12" aria-label="Prioridades e atividade recente">
          <div className="min-w-0 xl:col-span-7">
            <CriticalList students={critical.data?.students} loading={critical.isLoading} onSelect={(id) => setSelectedId(id)} />
            {critical.isError && <p role="alert" className="mt-2 text-xs text-red-700">Não foi possível consultar a fila crítica. <button type="button" onClick={() => void critical.refetch()} className="font-semibold underline underline-offset-2">Tentar novamente</button></p>}
          </div>
          <div className="min-w-0 xl:col-span-5"><RecentActivity logs={activity.data?.logs} loading={activity.isLoading} error={activity.isError} onRetry={() => void activity.refetch()} /></div>
        </section>

        {(model.data?.disclaimer || model.data?.training_data === "synthetic") && <Card className="border-neutral-200 bg-neutral-50 shadow-none"><CardContent className="flex items-start gap-3 p-4 text-xs text-neutral-600"><Info className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" /><div><p className="font-semibold text-neutral-900">Apoio à decisão da coordenação</p><p className="mt-1 leading-relaxed">{model.data?.disclaimer || copy.modelDisclaimerFallback}</p></div></CardContent></Card>}

        <div className="flex items-center justify-center gap-2 pb-1 text-[10px] text-neutral-400"><ShieldCheck className="h-3.5 w-3.5 text-[var(--brand-indigo)]" /> Dados e indicadores limitados à instituição autenticada.</div>
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}
