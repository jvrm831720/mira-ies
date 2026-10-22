"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ArrowUpRight, Database, Info, MessageSquareHeart, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { Header } from "@/components/layout/header";
import { KpiCards } from "@/components/risk/kpi-cards";
import { CriticalList } from "@/components/risk/critical-list";
import { RiskDistribution } from "@/components/risk/risk-distribution";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { copy } from "@/lib/copy";

const buttonPrimary = "inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[var(--brand-coral)] px-4 text-[13px] font-semibold text-[var(--brand-midnight)] shadow-sm transition hover:-translate-y-0.5 hover:bg-[#ff8a7c] focus-visible:outline-white";
const buttonSecondary = "inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 text-[13px] font-medium text-white transition hover:bg-white/15";

export default function CommandCenterPage() {
  const summary = useQuery({ queryKey: ["risk-summary"], queryFn: () => api.riskSummary() });
  const critical = useQuery({ queryKey: ["risk-critical"], queryFn: () => api.riskCritical(10) });
  const model = useQuery({ queryKey: ["model-info"], queryFn: () => api.modelInfo(), retry: false });
  const total = summary.data?.total_scored ?? (summary.data?.summary ? summary.data.summary.baixo + summary.data.summary.medio + summary.data.summary.critico : 0);
  const criticalCount = summary.data?.summary.critico ?? 0;
  const priorityRate = total ? Math.round((criticalCount / total) * 100) : 0;

  return (
    <>
      <Header title="Visão geral" subtitle="Acompanhe riscos e transforme sinais em cuidado próximo." />
      <main className="mx-auto w-full max-w-[1600px] space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <section className="relative isolate overflow-hidden rounded-[22px] bg-[var(--brand-midnight)] px-5 py-6 text-white shadow-[0_16px_44px_rgba(16,13,80,0.16)] sm:px-8 sm:py-8 lg:px-10">
          <div className="absolute -right-14 -top-28 -z-10 h-72 w-72 rounded-full border border-white/[0.08]" />
          <div className="absolute -right-4 -top-16 -z-10 h-52 w-52 rounded-full border border-white/[0.08]" />
          <div className="absolute bottom-0 right-[22%] -z-10 h-28 w-28 rounded-full bg-[var(--brand-indigo)]/25 blur-3xl" />
          <div className="absolute bottom-0 left-0 h-1 w-24 bg-[var(--brand-coral)]" />
          <div className="grid gap-7 lg:grid-cols-[minmax(0,1fr)_250px] lg:items-end">
            <div className="max-w-2xl">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.07] px-3 py-1.5 text-[11px] font-medium tracking-wide text-white/80">
                <Sparkles className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                INTELIGÊNCIA PARA PERMANÊNCIA ESTUDANTIL
              </div>
              <h2 className="max-w-xl text-[27px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-[34px]">
                Mais clareza para agir.<br className="hidden sm:block" /> Mais presença para cuidar.
              </h2>
              <p className="mt-3 max-w-lg text-[13px] leading-6 text-white/65 sm:text-sm">
                Veja quem precisa de atenção agora e organize o próximo passo da sua equipe, com os dados da sua instituição.
              </p>
              <div className="mt-6 flex flex-wrap gap-2.5">
                <Link href="/importar" className={buttonPrimary}><Upload className="h-4 w-4" /> Importar dados <ArrowRight className="ml-1 h-3.5 w-3.5" /></Link>
                <Link href="/retencao" className={buttonSecondary}><MessageSquareHeart className="h-4 w-4" /> Abrir retenção</Link>
              </div>
            </div>
            <div className="hidden rounded-2xl border border-white/10 bg-white/[0.06] p-4 lg:block">
              <div className="flex items-center gap-2 text-[11px] font-medium text-white/60"><ShieldCheck className="h-4 w-4 text-[var(--brand-coral)]" /> Sinal prioritário</div>
              <div className="mt-4 flex items-end justify-between gap-3">
                <div>
                  <p className="text-3xl font-semibold tracking-[-0.05em] tabular-nums">{summary.isLoading ? "—" : `${priorityRate}%`}</p>
                  <p className="mt-1 text-[11px] text-white/55">da base em risco crítico</p>
                </div>
                <Link href="/alunos?risk=critico" aria-label="Ver alunos em risco crítico" className="mb-1 grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-[var(--brand-coral)] transition hover:bg-white/15"><ArrowUpRight className="h-4 w-4" /></Link>
              </div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-[var(--brand-coral)] transition-[width]" style={{ width: `${summary.isLoading ? 0 : priorityRate}%` }} /></div>
              <p className="mt-2 text-[10px] text-white/45">{summary.isLoading ? "Carregando resumo" : `${criticalCount.toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")} alunos pontuados`}</p>
            </div>
          </div>
        </section>

        {summary.isError && (
          <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div><p className="font-medium">Não foi possível carregar o resumo agora.</p><p className="mt-0.5 text-xs text-red-800">Confira a conexão da instituição e tente atualizar a página.</p></div>
          </div>
        )}

        <section aria-label="Indicadores de risco" className="space-y-3">
          <div className="flex items-end justify-between gap-3">
            <div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">Sua base</p><h2 className="mt-1 text-base font-semibold tracking-tight">Indicadores de risco</h2></div>
            <Link href="/alunos" className="hidden items-center gap-1 text-xs font-medium text-primary hover:underline sm:flex">Ver lista de alunos <ArrowRight className="h-3.5 w-3.5" /></Link>
          </div>
          <KpiCards data={summary.data} loading={summary.isLoading} />
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
          <RiskDistribution data={summary.data} loading={summary.isLoading} />
          <CriticalList students={critical.data?.students} loading={critical.isLoading} />
        </section>

        <section className="grid gap-3 md:grid-cols-2">
          <Link href="/importar" className="group rounded-2xl border border-border/80 bg-white p-4 transition hover:border-primary/25 hover:shadow-soft">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef0ff] text-[var(--brand-indigo)]"><Database className="h-[18px] w-[18px]" /></span>
              <span className="min-w-0 flex-1"><span className="block text-[13px] font-semibold">Atualize sua base</span><span className="mt-0.5 block text-xs text-muted-foreground">Importe uma planilha para recalcular os sinais de risco.</span></span>
              <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
            </div>
          </Link>
          <Link href="/retencao" className="group rounded-2xl border border-border/80 bg-white p-4 transition hover:border-primary/25 hover:shadow-soft">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#fff0ed] text-[#e76e61]"><MessageSquareHeart className="h-[18px] w-[18px]" /></span>
              <span className="min-w-0 flex-1"><span className="block text-[13px] font-semibold">Planeje a próxima abordagem</span><span className="mt-0.5 block text-xs text-muted-foreground">Revise a régua de contato antes de iniciar uma simulação.</span></span>
              <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
            </div>
          </Link>
        </section>

        {(model.data?.disclaimer || model.data?.training_data === "synthetic") && (
          <Card className="border-[#e8e4d9] bg-[#fbfaf7] shadow-none">
            <CardContent className="flex items-start gap-3 p-4 text-xs text-[#5f594b]">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--brand-indigo)]" />
              <div><p className="font-semibold">Decisão apoiada por dados, cuidado conduzido por pessoas</p><p className="mt-1 leading-relaxed">{model.data?.disclaimer || copy.modelDisclaimerFallback}{model.data?.model_scope ? ` · Escopo: ${model.data.model_scope}` : ""}{model.data?.training_data ? ` · Dados: ${model.data.training_data}` : ""}</p></div>
            </CardContent>
          </Card>
        )}
        <p className="px-1 text-[10px] leading-relaxed text-muted-foreground">Os indicadores apoiam a priorização da equipe e não substituem a avaliação individual nem o acompanhamento humano.</p>
      </main>
    </>
  );
}
