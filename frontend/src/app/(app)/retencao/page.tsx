"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Activity, AlertTriangle, Check, CircleAlert, Mail, MessageCircle, Play, ShieldCheck, Smartphone } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { copy } from "@/lib/copy";
import type { RiskLevel, RetentionRunResult } from "@/types/api";

const levelOptions: { value: RiskLevel; title: string; detail: string; color: string }[] = [
  { value: "critico", title: "Crítico", detail: "Prioridade imediata", color: "var(--brand-coral)" },
  { value: "medio", title: "Médio", detail: "Acompanhamento próximo", color: "var(--brand-indigo)" },
  { value: "baixo", title: "Baixo", detail: "Sem contato pela régua", color: "var(--brand-blue)" },
];
const channelItems = [
  { key: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { key: "email", label: "E-mail", icon: Mail },
  { key: "sms", label: "SMS", icon: Smartphone },
] as const;

export default function RetencaoPage() {
  const queryClient = useQueryClient();
  const [dryRun, setDryRun] = useState(true);
  const [limit, setLimit] = useState(50);
  const [levels, setLevels] = useState<RiskLevel[]>(["critico"]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RetentionRunResult | null>(null);
  const status = useQuery({ queryKey: ["agents-status"], queryFn: () => api.agentsStatus() });

  function toggleLevel(level: RiskLevel) {
    setLevels((previous) => previous.includes(level) ? previous.filter((item) => item !== level) : [...previous, level]);
  }

  async function run() {
    if (levels.length === 0) {
      toast.error("Selecione ao menos um nível de risco.");
      return;
    }
    if (!dryRun && !window.confirm("Esta execução pode enviar WhatsApp, e-mail ou SMS reais para alunos elegíveis. Deseja continuar?")) return;
    setLoading(true);
    try {
      const response = await api.retentionRun({ risk_levels: levels, limit, dry_run: dryRun }, crypto.randomUUID());
      setResult(response);
      toast.success(dryRun ? "Simulação concluída." : "Execução concluída.");
      void queryClient.invalidateQueries({ queryKey: ["retention-logs"] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível executar a régua.");
    } finally {
      setLoading(false);
    }
  }

  const totals = result?.totals;
  const resultItems = [
    { label: "Simulados", value: totals?.dry_run ?? 0, color: "var(--brand-indigo)" },
    { label: "Enviados", value: totals?.sent ?? 0, color: "#348b65" },
    { label: "Ignorados", value: totals?.skipped ?? 0, color: "#73758a" },
    { label: "Falhas", value: (totals?.failed ?? 0) + (totals?.unknown ?? 0), color: "var(--brand-coral)" },
  ];
  const resultTotal = resultItems.reduce((sum, item) => sum + item.value, 0);

  return (
    <>
      <Header title="Retenção ativa" subtitle="Revise o público e a segurança antes de iniciar uma régua de contato." />
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <Card>
            <CardHeader>
              <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary"><span className="grid h-6 w-6 place-items-center rounded-lg bg-secondary">01</span> Público da régua</div>
              <CardTitle className="text-lg">Quem deve receber atenção?</CardTitle>
              <CardDescription>Escolha os níveis de risco e o tamanho máximo desta execução.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <fieldset>
                <legend className="mb-3 text-xs font-semibold">Níveis de risco</legend>
                <div className="grid gap-2 sm:grid-cols-3">
                  {levelOptions.map((option) => {
                    const selected = levels.includes(option.value);
                    return <button key={option.value} type="button" aria-pressed={selected} onClick={() => toggleLevel(option.value)} className={`relative flex min-h-[82px] items-start gap-3 rounded-xl border p-3.5 text-left transition ${selected ? "border-primary/35 bg-secondary/70 shadow-[0_0_0_2px_rgba(64,80,205,0.08)]" : "border-border bg-white hover:bg-muted/40"}`}>
                      <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border" style={selected ? { borderColor: option.color, backgroundColor: option.color, color: "white" } : undefined}>{selected && <Check className="h-3 w-3" />}</span>
                      <span><span className="block text-xs font-semibold">{option.title}</span><span className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">{option.detail}</span></span>
                    </button>;
                  })}
                </div>
              </fieldset>
              <div className="grid gap-5 border-t border-border pt-5 sm:grid-cols-2 sm:items-end">
                <label className="block space-y-2"><span className="text-xs font-semibold">Limite de alunos</span><input type="number" min={1} max={500} value={limit} onChange={(event) => setLimit(Math.min(500, Math.max(1, Number(event.target.value) || 1)))} className="h-11 w-full rounded-xl border border-input bg-white px-3.5 text-sm tabular-nums outline-none focus:ring-2 focus:ring-primary/25" /><span className="block text-[10px] text-muted-foreground">Máximo de 500 por execução.</span></label>
                <p className="flex items-start gap-2 rounded-xl bg-muted/35 p-3 text-[11px] leading-relaxed text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />As regras de anti-spam e o opt-out continuam ativos durante a execução.</p>
              </div>
            </CardContent>
          </Card>

          <aside className="space-y-4">
            <Card className="bg-[var(--brand-midnight)] text-white shadow-none">
              <CardHeader className="pb-3"><div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/60"><span className="grid h-6 w-6 place-items-center rounded-lg bg-white/10 text-[var(--brand-coral)]">02</span> Modo de envio</div><CardTitle className="text-base text-white">Comece com segurança</CardTitle><CardDescription className="text-white/60">Simulação é a opção recomendada para revisar a régua.</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                <label className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.06] p-3.5">
                  <span><span className="block text-xs font-semibold">Modo simulação</span><span className="mt-0.5 block text-[10px] text-white/55">Nenhuma mensagem real é enviada</span></span>
                  <input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} aria-label="Executar em modo simulação" className="h-5 w-5 accent-[#f47769]" />
                </label>
                <div className="space-y-2 rounded-xl border border-white/10 px-3.5 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/45">Canais configurados</p>
                  {channelItems.map(({ key, label, icon: Icon }) => <div key={key} className="flex items-center justify-between text-xs"><span className="flex items-center gap-2 text-white/75"><Icon className="h-3.5 w-3.5 text-[var(--brand-coral)]" />{label}</span><span className="rounded-md bg-white/10 px-2 py-1 text-[10px] font-medium text-white/75">{status.data?.providers[key] ?? (status.isLoading ? "verificando" : "—")}</span></div>)}
                </div>
                <Button onClick={run} disabled={loading || levels.length === 0} className="w-full bg-[var(--brand-coral)] text-[var(--brand-midnight)] hover:bg-[#ff8a7c]">{loading ? <Activity className="h-4 w-4 animate-pulse" /> : <Play className="h-4 w-4" />}{loading ? "Executando…" : dryRun ? "Simular contatos" : "Revisar e executar"}</Button>
              </CardContent>
            </Card>
            {dryRun ? <div className="flex items-start gap-2.5 rounded-xl border border-[#dce0ff] bg-[#f3f4ff] p-3.5 text-xs leading-relaxed text-[#313e9e]"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /><span>{copy.dryRunBanner}</span></div> : <div className="flex items-start gap-2.5 rounded-xl border border-[#f4d4ce] bg-[#fff4f1] p-3.5 text-xs leading-relaxed text-[#963b32]"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" /><span>Modo real ativo. Confira os níveis de risco e confirme apenas quando estiver pronto para contatar alunos.</span></div>}
            {!dryRun && status.data?.dry_run_default && <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground"><AlertTriangle className="h-3 w-3" />O ambiente usa simulação por padrão; esta execução solicita modo real.</p>}
          </aside>
        </div>

        {result && <Card className="overflow-hidden"><div className="h-1 bg-primary" /><CardHeader className="flex-row items-start justify-between gap-4"><div><CardTitle>Resumo da execução</CardTitle><CardDescription className="mt-1">{result.message || "Execução finalizada"} · {result.dry_run ? "Simulação" : "Modo real"}</CardDescription></div><span className="rounded-full bg-secondary px-3 py-1 text-[10px] font-semibold text-primary">{resultTotal.toLocaleString("pt-BR")} registros</span></CardHeader><CardContent className="space-y-5">
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{resultItems.map((item) => <div key={item.label} className="rounded-xl border border-border/80 p-4"><p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{item.label}</p><p className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: item.color }}>{item.value.toLocaleString("pt-BR")}</p><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full" style={{ width: `${resultTotal ? (item.value / resultTotal) * 100 : 0}%`, backgroundColor: item.color }} /></div></div>)}</div>
          {result.by_channel && <div className="border-t border-border pt-4"><h3 className="mb-3 text-xs font-semibold">Detalhamento por canal</h3><div className="grid gap-2 sm:grid-cols-3">{Object.entries(result.by_channel).map(([channel, stats]) => <div key={channel} className="rounded-xl bg-muted/35 px-3.5 py-3"><p className="text-xs font-semibold capitalize">{channel}</p><p className="mt-1 text-[10px] text-muted-foreground">{Object.entries(stats).map(([label, value]) => `${label}: ${value}`).join(" · ")}</p></div>)}</div></div>}
        </CardContent></Card>}
      </main>
    </>
  );
}
