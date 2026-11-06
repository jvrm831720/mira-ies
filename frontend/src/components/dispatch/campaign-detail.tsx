"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ExternalLink, X } from "@/components/ui/icons";
import { dispatchApi, type DispatchCampaign } from "@/lib/dispatch-api";
import { CHANNEL_LABEL, ITEM_STATUS_LABEL, PURPOSE_LABEL, CAMPAIGN_STATUS_LABEL } from "./dispatch-types";
import { MAX_ITEMS_PREVIEW, readableDate } from "./dispatch-utils";

type DispatchItem = {
  id: string; status: string; subject_type: string; subject_ref: string;
  channel: string; attempt: number; scheduled_for?: string | null;
  updated_at?: string | null; last_error?: string | null;
};
type DetailTab = "properties" | "items" | "replies";
const tabs: Array<{id:DetailTab;title:string}> = [
  { id:"properties",title:"Propriedades" },
  { id:"items",title:"Itens e tentativas" },
  { id:"replies",title:"Respostas" },
];
const safeStatus = (v:string) => ITEM_STATUS_LABEL[v] || "Estado não reconhecido";
function Row({ title, value }: { title:string;value:ReactNode }) {
  return <div className="grid grid-cols-[minmax(0,130px)_minmax(0,1fr)] gap-3 border-b border-[var(--color-border-subtle)] py-2.5 text-[12px]">
    <dt className="text-[var(--color-muted)]">{title}</dt>
    <dd className="min-w-0 break-words font-medium text-[var(--color-ink)]">{value}</dd>
  </div>;
}
export function CampaignDetailDrawer({
  campaign, tenantId, userId, onClose, onOpenMonitor,
}:{
  campaign: DispatchCampaign; tenantId: string; userId: string;
  onClose: ()=>void; onOpenMonitor: ()=>void;
}) {
  const [tab,setTab] = useState<DetailTab>("properties");
  const [page,setPage] = useState(0);
  const panelRef = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(()=>{
    previousFocus.current = document.activeElement as HTMLElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    function keydown(event:KeyboardEvent) {
      if(event.key === "Escape") {event.preventDefault();onClose();}
      if(event.key !== "Tab" || !panelRef.current) return;
      const nodes = [...panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled], [tabindex="-1"])'
      )].filter(n=>n.getClientRects().length>0);
      if(!nodes.length)return;
      const first=nodes[0],last=nodes[nodes.length-1];
      if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
    }
    document.addEventListener("keydown",keydown);
    return ()=>{document.body.style.overflow=oldOverflow; document.removeEventListener("keydown",keydown);previousFocus.current?.focus();};
  },[onClose]);
  const detail=useQuery({
    queryKey:["dispatch","campaign-detail",tenantId,userId,campaign.id],
    queryFn:()=>dispatchApi.detail(campaign.id),
    enabled:!!tenantId && !!userId,
    staleTime:15_000,retry:false,
  });
  const replies=useQuery({
    queryKey:["dispatch","campaign-replies",tenantId,userId,campaign.id],
    queryFn:()=>dispatchApi.replies(campaign.id),
    enabled:tab==="replies" && !!tenantId && !!userId,
    staleTime:15_000,retry:false,
  });
  const current=detail.data?.campaign||campaign;
  const items=(detail.data?.items||[]) as DispatchItem[];
  const visible=items.slice(page*25,(page+1)*25);
  return <div className="fixed inset-0 z-[90] flex justify-end" aria-label="Detalhes da campanha">
    <button type="button" aria-label="Fechar detalhe da campanha" tabIndex={-1} onClick={onClose}
      className="absolute inset-0 cursor-default bg-[var(--color-ink)]/35" />
    <aside ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="campaign-drawer-title"
      className="relative z-10 flex h-full w-full max-w-[600px] flex-col overflow-hidden border-l border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)] outline-none">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-3">
        <p className="text-[11px] text-[var(--color-muted)]">Operação / Campanha operacional</p>
        <button type="button" onClick={onClose} aria-label="Fechar painel" className="grid h-8 w-8 place-items-center rounded-md hover:bg-[var(--color-panel)]"><X className="h-4 w-4" /></button>
      </div>
      <div className="border-b border-[var(--color-border)] px-5 py-5">
        <h2 id="campaign-drawer-title" className="text-[18px] font-semibold tracking-tight">{current.name}</h2>
        <p className="mt-2 text-[11px] text-[var(--color-slate-600)]">
          {PURPOSE_LABEL[current.purpose]} · {CHANNEL_LABEL[current.channel]} · {CAMPAIGN_STATUS_LABEL[current.status] || current.status}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href="/workflows" className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[12px] hover:bg-[var(--color-panel)]">
            Ver Workflows <ExternalLink className="h-3.5 w-3.5"/>
          </Link>
          <button type="button" onClick={()=>{onClose();onOpenMonitor();}} className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-ink)] px-3 text-[12px] font-medium text-white">
            Ver fila <ArrowRight className="h-3.5 w-3.5"/>
          </button>
        </div>
      </div>
      <nav aria-label="Seções da campanha" className="flex border-b border-[var(--color-border)] px-5">
        {tabs.map(t=><button key={t.id} type="button" onClick={()=>setTab(t.id)} aria-current={tab===t.id?"page":undefined}
          className={"border-b-2 px-3 py-3 text-[12px] "+(tab===t.id?"border-[var(--color-blue)] font-semibold text-[var(--color-blue)]":"border-transparent text-[var(--color-slate-600)]")}>{t.title}</button>)}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-8">
        {detail.isLoading && <p role="status" className="py-5 text-[12px] text-[var(--color-muted)]">Carregando dados autorizados…</p>}
        {detail.isError && <p role="alert" className="py-5 text-[12px] text-[var(--color-red)]">Não foi possível consultar o detalhe. <button className="underline" onClick={()=>void detail.refetch()} type="button">Tentar novamente</button></p>}
        {!detail.isError && tab==="properties" && <dl className="mt-4">
          <Row title="Identificador" value={<code className="break-all text-[11px]">{current.id}</code>} />
          <Row title="Finalidade" value={PURPOSE_LABEL[current.purpose]} />
          <Row title="Canal" value={CHANNEL_LABEL[current.channel]} />
          <Row title="Estado" value={CAMPAIGN_STATUS_LABEL[current.status] || current.status} />
          <Row title="Modelo" value={current.template_ref || "Não registrado"} />
          <Row title="Tipo de audiência" value={current.delivery_mode} />
          <Row title="Origem" value={current.source_kind || "Não registrada"} />
          <Row title="Referência da origem" value={current.source_ref || "Não registrada"} />
          <Row title="Proposta relacionada" value={current.origin_proposal_id || "Nenhum vínculo explícito"} />
          <Row title="Criada em" value={readableDate(current.created_at)} />
          <Row title="Agendada para" value={readableDate(current.scheduled_for)} />
          <Row title="Aprovada em" value={readableDate(current.approved_at)} />
          <Row title="Fila (agregada)" value={campaign.pending} />
          <Row title="Pós-envio (agregado)" value={campaign.accepted} />
          <Row title="Problemas (agregados)" value={campaign.problems} />
          <p className="mt-4 text-[11px] leading-relaxed text-[var(--color-muted)]">Campanhas operacionais são distintas das propostas de aprovação. Nenhum clique neste painel cria, aprova, agenda ou executa mensagens.</p>
        </dl>}
        {!detail.isError && tab==="items" && <section className="mt-4 space-y-3">
          <div className="flex items-start gap-2 rounded-md bg-[var(--color-panel)] p-3 text-[11px] text-[var(--color-slate-600)]">
            <AlertTriangle className="h-4 w-4 shrink-0" />Até {MAX_ITEMS_PREVIEW} itens recentes: não extrapolar filtros ou contagens à operação inteira. Identificadores pessoais e erros brutos não são exibidos.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-[11px]">
              <thead><tr className="border-b border-[var(--color-border)] bg-[var(--color-panel)]">
                <th scope="col" className="px-2 py-2">Item</th><th scope="col" className="px-2 py-2">Estado</th>
                <th scope="col" className="px-2 py-2">Tentativas</th><th scope="col" className="px-2 py-2">Atualizado</th>
              </tr></thead>
              <tbody>{visible.map(item=><tr key={item.id} className="border-b border-[var(--color-border-subtle)]">
                <td className="px-2 py-3 font-mono">{item.id.slice(0,8)}…</td>
                <td className="px-2 py-3">{safeStatus(item.status)}
                  {!!item.last_error && <span className="block text-[10px] text-[var(--color-red)]">Erro registrado (detalhe oculto)</span>}
                </td>
                <td className="px-2 py-3 tabular-nums">{item.attempt}</td><td className="px-2 py-3">{readableDate(item.updated_at)}</td>
              </tr>)}</tbody>
            </table>
          </div>
          {!items.length && !detail.isLoading && <p className="py-4 text-[12px] text-[var(--color-muted)]">Nenhum item retornado.</p>}
          {items.length>25 && <div className="flex items-center justify-end gap-3 text-[11px]">
            <button type="button" disabled={page===0} onClick={()=>setPage(i=>i-1)} className="disabled:opacity-40">Anterior</button>
            <span>{page+1} de {Math.ceil(items.length/25)}</span>
            <button type="button" disabled={(page+1)*25>=items.length} onClick={()=>setPage(i=>i+1)} className="disabled:opacity-40">Próxima</button>
          </div>}
        </section>}
        {tab==="replies" && <section className="mt-4 space-y-3">
          {replies.isLoading && <p role="status" className="text-[12px] text-[var(--color-muted)]">Consultando respostas…</p>}
          {replies.isError && <p role="alert" className="text-[12px] text-[var(--color-red)]">Respostas indisponíveis. <button type="button" onClick={()=>void replies.refetch()} className="underline">Tentar novamente</button></p>}
          {replies.data?.items.map((reply,index)=><article key={index} className="border-b border-[var(--color-border)] py-3 text-[12px]">
            <p className="font-medium">{reply.event_kind}</p>
            <p className="mt-1 text-[11px] text-[var(--color-muted)]">{readableDate(reply.occurred_at)}</p>
            <p className="mt-1 text-[11px] text-[var(--color-slate-600)]">{reply.reply_intent || "Intenção não classificada"}</p>
          </article>)}
          {!replies.isLoading && replies.data?.items.length===0 && <p className="py-4 text-[12px] text-[var(--color-muted)]">Nenhuma resposta registrada.</p>}
          <p className="text-[11px] text-[var(--color-muted)]">Uma resposta não comprova pagamento, acordo, entrega ou permanência.</p>
        </section>}
      </div>
    </aside>
  </div>;
}
