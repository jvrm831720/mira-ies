import { Activity, AlertCircle, CheckCircle2, Mail, MessageCircle, ShieldCheck, Smartphone, Zap } from "@/components/ui/icons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AgentsStatus, ModelInfo } from "@/types/api";

const channelMeta = [
  { key: "whatsapp", label: "WhatsApp", Icon: MessageCircle },
  { key: "email", label: "E-mail", Icon: Mail },
  { key: "sms", label: "SMS", Icon: Smartphone },
] as const;
const providerLabels: Record<string, string> = { dry_run: "Simulação", waha: "WAHA", evolution: "Evolution API", resend: "Resend", twilio: "Twilio" };
function providerLabel(provider: string) { return providerLabels[provider] || provider.replaceAll("_", " "); }

export function OperationalOverview({ model, agents, modelLoading, agentsLoading, modelError, agentsError }: {
  model?: ModelInfo; agents?: AgentsStatus; modelLoading?: boolean; agentsLoading?: boolean; modelError?: boolean; agentsError?: boolean;
}) {
  const modelReady = model?.status === "ready";
  const dryRun = agents?.dry_run_default !== false;
  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 border-b border-black/[0.06] pb-4">
        <div><CardTitle className="text-[17px] tracking-[-0.03em]">Saúde da operação</CardTitle><CardDescription className="mt-1">Modelo preditivo e configuração da régua</CardDescription></div>
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-[rgba(64,80,205,0.09)] text-[var(--brand-indigo)]"><Activity className="h-4 w-4" /></span>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-black/[0.055] bg-[var(--brand-paper)] p-4">
            <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-xl bg-white text-[var(--brand-indigo)] shadow-sm"><Zap className="h-4 w-4" /></span><span className="text-[11px] font-semibold text-neutral-600">Motor preditivo</span></div>
            {modelLoading ? <Skeleton className="mt-4 h-5 w-28" /> : modelError ? <div className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-[#b84336]"><AlertCircle className="h-3.5 w-3.5" /> Status indisponível</div> : <>
              <p className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-neutral-900">{modelReady ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertCircle className="h-4 w-4 text-amber-600" />}{modelReady ? "Disponível" : model?.status === "error" ? "Requer atenção" : "Não confirmado"}</p>
              <p className="mt-1 truncate text-[10px] text-neutral-500" title={model?.version || undefined}>{model?.version ? `Versão ${model.version}` : model?.model_scope === "tenant" ? "Modelo da instituição" : "Modelo base"}</p>
            </>}
          </div>
          <div className="rounded-2xl border border-black/[0.055] bg-[var(--brand-paper)] p-4">
            <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-xl bg-white text-[var(--brand-indigo)] shadow-sm"><ShieldCheck className="h-4 w-4" /></span><span className="text-[11px] font-semibold text-neutral-600">Modo de execução</span></div>
            {agentsLoading ? <Skeleton className="mt-4 h-5 w-32" /> : agentsError ? <div className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-[#b84336]"><AlertCircle className="h-3.5 w-3.5" /> Status indisponível</div> : <>
              <p className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-neutral-900"><span className={`h-2 w-2 rounded-full ${dryRun ? "bg-emerald-500" : "bg-amber-500"}`} />{dryRun ? "Simulação por padrão" : "Execução ativa por padrão"}</p>
              <p className="mt-1 text-[10px] text-neutral-500">{dryRun ? "Nenhuma mensagem real por padrão" : "Verifique as credenciais e as políticas antes de executar"}</p>
            </>}
          </div>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between gap-2"><p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-neutral-400">Canais de comunicação</p><span className="text-[10px] text-neutral-400">Configuração atual</span></div>
          {agentsLoading ? <div className="grid gap-2 sm:grid-cols-3"><Skeleton className="h-[66px] rounded-xl" /><Skeleton className="h-[66px] rounded-xl" /><Skeleton className="h-[66px] rounded-xl" /></div>
            : agentsError || !agents ? <div className="rounded-xl border border-dashed border-neutral-200 px-3 py-4 text-center text-xs text-neutral-500">Não foi possível consultar a configuração dos canais.</div>
            : <div className="grid gap-2 sm:grid-cols-3">{channelMeta.map(({ key, label, Icon }) => {
              const provider = agents.providers[key];
              const simulated = provider === "dry_run";
              return <div key={key} className="flex min-w-0 items-center gap-2.5 rounded-xl border border-black/[0.055] bg-white px-3 py-3">
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${simulated ? "bg-neutral-100 text-neutral-500" : "bg-[rgba(64,80,205,0.09)] text-[var(--brand-indigo)]"}`}><Icon className="h-4 w-4" /></span>
                <div className="min-w-0"><p className="truncate text-[11px] font-semibold text-neutral-800">{label}</p><p className={`mt-0.5 truncate text-[10px] ${simulated ? "text-neutral-400" : "text-emerald-700"}`}>{providerLabel(provider)}</p></div>
              </div>;
            })}</div>}
        </div>
        <div className="flex items-start gap-2 rounded-xl border border-[rgba(64,80,205,0.12)] bg-[rgba(64,80,205,0.045)] px-3 py-2.5"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-indigo)]" /><p className="text-[10px] leading-relaxed text-neutral-600">Este painel informa a configuração; não envia mensagens. Campanhas de retenção continuam em modo simulado.</p></div>
      </CardContent>
    </Card>
  );
}
