"use client";
import { AlertTriangle, BarChart3, CreditCard, ShieldCheck } from "@/components/ui/icons";
import type { DispatchMetrics, DispatchPaymentResults } from "@/lib/dispatch-api";

function Indicator({label,value,note}:{label:string;value?:number|null;note:string}) {
  return <div className="border-b border-r border-[var(--color-border)] p-4">
    <p className="text-[11px] text-[var(--color-slate-600)]">{label}</p>
    <p className="mt-2 text-[21px] font-semibold tabular-nums">{value==null ? "—" : value.toLocaleString("pt-BR")}</p>
    <p className="mt-1 text-[10px] leading-relaxed text-[var(--color-muted)]">{note}</p>
  </div>;
}
export function DispatchResults({
  metrics, financial, canAudit, financialLoading, financialError,
}:{
  metrics: DispatchMetrics | null;
  financial: DispatchPaymentResults | null;
  canAudit: boolean;
  financialLoading: boolean;
  financialError: boolean;
}) {
  return <div className="space-y-5">
    <section className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
      <header className="border-b border-[var(--color-border)] p-5">
        <div className="flex items-center gap-2"><BarChart3 className="h-4 w-4 text-[var(--color-slate-600)]"/><h2 className="text-[13px] font-semibold">Evidências de comunicação</h2></div>
        <p className="mt-1 text-[11px] text-[var(--color-muted)]">Contagens globais do motor, sem extrapolação financeira ou acadêmica.</p>
      </header>
      {!metrics ? <p className="p-5 text-[12px] text-[var(--color-muted)]">Não foi possível consultar os indicadores.</p> : <div className="grid grid-cols-2 md:grid-cols-3">
        <Indicator label="Pós-envio (agregado)" value={metrics.accepted} note="Inclui aceitos, entregues, lidos e respondidos; não representa entregas confirmadas." />
        <Indicator label="Na fila / em processamento" value={metrics.queued} note="Não equivale a envio concluído." />
        <Indicator label="Respostas registradas" value={metrics.replies} note="Resposta não é confirmação de resultado." />
        <Indicator label="Falhas / bloqueios / desconhecidos" value={metrics.problems} note="Agrupamento operacional; requer investigação." />
        <Indicator label="Simulações" value={metrics.simulated} note="Não são mensagens reais." />
        <Indicator label="Campanhas" value={metrics.campaigns} note="Campanhas operacionais registradas, não propostas." />
      </div>}
      <p className="flex items-start gap-2 border-t border-[var(--color-border)] bg-[var(--color-panel)] p-4 text-[11px] leading-relaxed text-[var(--color-slate-600)]">
        <AlertTriangle className="h-4 w-4 shrink-0"/> O endpoint atual não distingue globalmente aceito, entregue e lido. A MIRA não exibe percentuais inventados de entrega, abertura ou resposta.
      </p>
    </section>
    <section className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5">
      <div className="flex items-center gap-2"><CreditCard className="h-4 w-4 text-[var(--color-slate-600)]"/><h2 className="text-[13px] font-semibold">Recuperação financeira confirmada</h2></div>
      {!canAudit ? <p className="mt-3 text-[12px] text-[var(--color-muted)]">Dados financeiros ocultos: a permissão audit.view não está disponível nesta sessão.</p>
      : financialLoading ? <p role="status" className="mt-3 text-[12px] text-[var(--color-muted)]">Consultando resultados autorizados…</p>
      : financialError || !financial ? <p role="alert" className="mt-3 text-[12px] text-[var(--color-red)]">Não foi possível verificar os resultados financeiros.</p>
      : <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-4">
          <p className="text-[11px] text-[var(--color-slate-600)]">Transações verificadas</p>
          <p className="mt-1 text-[20px] font-semibold tabular-nums">{financial.payments.transactions.toLocaleString("pt-BR")}</p>
        </div>
        <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-4">
          <p className="text-[11px] text-[var(--color-slate-600)]">Recebimentos confirmados</p>
          <p className="mt-1 text-[20px] font-semibold tabular-nums">{new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(financial.payments.received_brl)}</p>
        </div>
        <p className="sm:col-span-2 text-[11px] text-[var(--color-muted)]">{financial.note}</p>
      </div>}
      <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-[var(--color-slate-600)]"><ShieldCheck className="h-4 w-4 shrink-0"/> Sem inferências: promessa, resposta e entrega não se convertem em pagamento sem conciliação verificável.</p>
    </section>
  </div>;
}
