"use client";
import { useMemo, useState } from "react";
import { AlertTriangle, Clock3, MessageCircle, Search } from "@/components/ui/icons";
import type { DispatchCampaign, DispatchMetrics } from "@/lib/dispatch-api";
import { CAMPAIGN_STATUS_LABEL, CHANNEL_LABEL } from "./dispatch-types";
import { MAX_CAMPAIGN_PREVIEW, readableDate } from "./dispatch-utils";

export function DispatchControlCenter({
  campaigns, metrics, onSelect, loading, error,
}:{
  campaigns:DispatchCampaign[];metrics:DispatchMetrics|null;
  onSelect:(item:DispatchCampaign)=>void;loading:boolean;error:boolean;
}) {
  const [query,setQuery]=useState("");
  const [status,setStatus]=useState("all");
  const filtered=useMemo(()=>campaigns.filter(item=>(status==="all"||item.status===status)
    && (!query || item.name.toLocaleLowerCase("pt-BR").includes(query.trim().toLocaleLowerCase("pt-BR")))),[campaigns,query,status]);
  return <section className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
    <div className="border-b border-[var(--color-border)] p-5">
      <h2 className="text-[13px] font-semibold">Controle de Dispatch</h2>
      <p className="mt-1 text-[11px] text-[var(--color-muted)]">Acompanhe a execução. Ações de envio dependem das permissões e dos gates existentes.</p>
    </div>
    {metrics && <div className="grid grid-cols-2 gap-px border-b border-[var(--color-border)] bg-[var(--color-border)] md:grid-cols-4">
      {([
        ["Na fila",metrics.queued],["Pós-envio agregado",metrics.accepted],
        ["Problemas",metrics.problems],["Respostas",metrics.replies],
      ] as Array<[string,number]>).map(([name,value])=><div className="bg-white p-4" key={name}>
        <p className="text-[11px] text-[var(--color-muted)]">{name}</p><p className="mt-1 text-[18px] font-semibold tabular-nums">{value.toLocaleString("pt-BR")}</p>
      </div>)}
    </div>}
    <div className="grid min-h-[330px] lg:grid-cols-[290px_minmax(0,1fr)]">
      <section className="border-b border-[var(--color-border)] lg:border-b-0 lg:border-r" aria-label="Operações visíveis">
        <div className="space-y-2 border-b border-[var(--color-border)] p-3">
          <label className="relative block"><Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[var(--color-muted)]"/>
            <input className="h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] pl-8 pr-2 text-[12px]" value={query}
              onChange={e=>setQuery(e.target.value)} aria-label="Buscar operações" placeholder="Buscar operação…" /></label>
          <select aria-label="Estado da operação" value={status} onChange={e=>setStatus(e.target.value)}
            className="h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] px-2 text-[12px]">
            <option value="all">Todos os estados</option>
            {(["draft","approved","scheduled","running","paused","completed","cancelled"] as const).map(s=><option value={s} key={s}>{CAMPAIGN_STATUS_LABEL[s]}</option>)}
          </select>
        </div>
        <div className="max-h-[560px] overflow-y-auto">
          {filtered.map(item=><button type="button" key={item.id} onClick={()=>onSelect(item)}
            className="block w-full border-b border-[var(--color-border-subtle)] p-3 text-left hover:bg-[var(--color-panel)] focus-visible:outline-2 focus-visible:outline-[var(--color-blue)]">
            <span className="block truncate text-[12px] font-semibold">{item.name}</span>
            <span className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-[var(--color-muted)]">
              {CAMPAIGN_STATUS_LABEL[item.status]} · {CHANNEL_LABEL[item.channel]}
            </span>
            <span className="mt-1 block text-[10px] tabular-nums text-[var(--color-slate-600)]">{item.pending} na fila · {item.problems} com problemas</span>
          </button>)}
          {!loading && !error && !filtered.length && <p className="p-5 text-[12px] text-[var(--color-muted)]">Nenhuma operação neste recorte.</p>}
          {loading && <p role="status" className="p-5 text-[12px] text-[var(--color-muted)]">Carregando campanhas…</p>}
          {error && <p role="alert" className="p-5 text-[12px] text-[var(--color-red)]">Não foi possível consultar as operações.</p>}
        </div>
        {campaigns.length===MAX_CAMPAIGN_PREVIEW && <p role="note" className="border-t border-[var(--color-border)] p-3 text-[10px] text-[var(--color-muted)]">Somente 50 campanhas recentes; não é listagem exaustiva.</p>}
      </section>
      <section className="space-y-5 p-5" aria-label="Contexto da operação">
        <div className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-[var(--color-slate-600)]"/><h3 className="text-[13px] font-semibold">Estados verificáveis</h3></div>
        <p className="text-[12px] leading-relaxed text-[var(--color-slate-600)]">Selecione uma campanha à esquerda para consultar propriedades, itens, tentativas e respostas no painel lateral. Nenhum evento é produzido pela simples abertura de um registro.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-4">
            <MessageCircle className="h-4 w-4 text-[var(--color-blue)]" />
            <p className="mt-2 text-[12px] font-medium">Aceito não é entregue</p>
            <p className="mt-1 text-[11px] text-[var(--color-muted)]">A API agrega estados pós-envio. Consulte cada item para verificar a evidência disponível.</p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-4">
            <AlertTriangle className="h-4 w-4 text-[var(--color-red)]" />
            <p className="mt-2 text-[12px] font-medium">Resultado desconhecido</p>
            <p className="mt-1 text-[11px] text-[var(--color-muted)]">Não repita envios automaticamente. O motor controla idempotência e reconciliação.</p>
          </div>
        </div>
        <dl className="grid gap-2 text-[11px] text-[var(--color-slate-600)]">
          <div className="flex justify-between border-b border-[var(--color-border)] pb-2"><dt>Worker observado</dt><dd>{metrics?.worker_online ? "Sim" : "Não confirmado"}</dd></div>
          <div className="flex justify-between border-b border-[var(--color-border)] pb-2"><dt>Última atividade</dt><dd>{readableDate(metrics?.worker_last_seen)}</dd></div>
          <div className="flex justify-between border-b border-[var(--color-border)] pb-2"><dt>Origem dos números</dt><dd>Ledger do tenant</dd></div>
        </dl>
        <p className="text-[11px] text-[var(--color-muted)]">Para ações administrativas ou preparação de contatos individuais, mantenha as etapas de autorização e MFA do console operacional existente.</p>
      </section>
    </div>
  </section>;
}
