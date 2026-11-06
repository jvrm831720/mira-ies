"use client";
import Link from "next/link";
import { Activity, AlertTriangle, BarChart3, Clock3, MessageCircle, RefreshCw } from "@/components/ui/icons";
import type { DispatchCampaign, DispatchMetrics } from "@/lib/dispatch-api";
import type { DispatchSection } from "./dispatch-types";
import { countCampaignPreview, readableDate } from "./dispatch-utils";

function Count({ value }: { value?: number | null }) {
  return <span className="text-[22px] font-semibold tracking-tight tabular-nums text-[var(--color-ink)]">
    {typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("pt-BR") : "—"}
  </span>;
}
function Metric({
  title, value, description, icon: Icon,
}: { title: string; value?: number | null; description: string; icon: typeof Activity }) {
  return <div className="min-w-0 border-r border-b border-[var(--color-border)] px-4 py-4 last:border-r-0 md:px-5">
    <div className="flex items-center justify-between gap-2 text-[11px] font-medium text-[var(--color-slate-600)]">
      <span>{title}</span><Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
    </div>
    <div className="mt-1"><Count value={value} /></div>
    <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-muted)]">{description}</p>
  </div>;
}
export function DispatchOverview({
  metrics, campaigns, loading, failed, onRetry, onChange,
}: {
  metrics: DispatchMetrics | null;
  campaigns: DispatchCampaign[];
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  onChange: (tab: DispatchSection) => void;
}) {
  const preview = countCampaignPreview(campaigns);
  return <div className="space-y-6">
    <section aria-label="Indicadores operacionais reais" className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-4">
        <div><h2 className="text-[13px] font-semibold">Estado atual da operação</h2>
          <p className="mt-1 text-[11px] text-[var(--color-muted)]">Dados do ledger de Dispatch; não são resultados financeiros nem acadêmicos.</p>
        </div>
        <button type="button" onClick={onRetry} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-3 text-[11px] font-medium hover:bg-[var(--color-panel)]">
          <RefreshCw className="h-3.5 w-3.5" /> Atualizar
        </button>
      </div>
      {loading ? <div role="status" className="p-6 text-[12px] text-[var(--color-muted)]">Consultando indicadores…</div>
      : failed || !metrics ? <div role="alert" className="p-6 text-[12px] text-[var(--color-red)]">Indicadores indisponíveis. Nenhum valor foi estimado.</div>
      : <div className="grid grid-cols-2 lg:grid-cols-3">
        <Metric title="Campanhas registradas" value={metrics.campaigns} icon={Activity} description="Contagem global autorizada deste workspace." />
        <Metric title="Itens pendentes" value={metrics.queued} icon={Clock3} description="Fila, tentativas e itens em processamento agregados." />
        <Metric title="Pós-envio (agregado)" value={metrics.accepted} icon={MessageCircle} description="Aceitos, entregues, lidos e respondidos juntos; NÃO comprova entrega." />
        <Metric title="Problemas" value={metrics.problems} icon={AlertTriangle} description="Bloqueios, falhas ou resultados desconhecidos." />
        <Metric title="Respostas registradas" value={metrics.replies} icon={MessageCircle} description="Resposta não comprova pagamento ou permanência." />
        <Metric title="Simulações" value={metrics.simulated} icon={BarChart3} description="Nenhuma mensagem real é inferida a partir de simulação." />
      </div>}
    </section>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <section aria-label="Campanhas que precisam de atenção" className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-4">
          <div><h2 className="text-[13px] font-semibold">Prioridades visíveis</h2><p className="mt-1 text-[11px] text-[var(--color-muted)]">Amostra de até 50 campanhas; não representa estatística global por estado.</p></div>
          <button type="button" onClick={() => onChange("campaigns")} className="text-[11px] font-medium text-[var(--color-blue)] hover:underline">Explorar campanhas</button>
        </div>
        {campaigns.filter(item => item.problems > 0 || item.status === "paused").slice(0, 6).map(item =>
          <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-subtle)] px-5 py-3 last:border-b-0">
            <div className="min-w-0"><p className="truncate text-[12px] font-medium">{item.name}</p><p className="mt-0.5 text-[10px] text-[var(--color-muted)]">{readableDate(item.created_at)} · {item.channel}</p></div>
            <span className="text-[11px] tabular-nums text-[var(--color-red)]">{item.problems > 0 ? item.problems + " itens com problema" : "Pausada"}</span>
          </div>)}
        {!loading && preview.withProblems === 0 && preview.paused === 0 &&
          <p className="px-5 py-7 text-[12px] text-[var(--color-muted)]">Nenhuma campanha problemática identificada entre os registros carregados.</p>}
      </section>
      <section aria-label="Condições do processamento" className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5">
        <h2 className="text-[13px] font-semibold">Processamento</h2>
        <div className="mt-4 flex items-center gap-2">
          <span className={"h-2 w-2 rounded-full " + (metrics?.worker_online ? "bg-[var(--color-green)]" : "bg-[var(--color-muted)]")} />
          <span className="text-[12px]">{metrics?.worker_online ? "Worker observado" : "Worker não confirmado"}</span>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-muted)]">
          Última atividade: {readableDate(metrics?.worker_last_seen)}. A presença do worker não autoriza nenhum disparo.
        </p>
        <div className="my-4 border-t border-[var(--color-border)]" />
        <button type="button" onClick={() => onChange("monitor")} className="text-[12px] font-medium text-[var(--color-blue)] hover:underline">Examinar fila e entregas</button>
        <div className="mt-4 border-t border-[var(--color-border)] pt-4">
          <Link href="/workflows" className="text-[12px] font-medium text-[var(--color-blue)] hover:underline">Abrir Workflows</Link>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-muted)]">Revisão de propostas e automações existentes; não implica execução.</p>
        </div>
      </section>
    </div>
  </div>;
}
