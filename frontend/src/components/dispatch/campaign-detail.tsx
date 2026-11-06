"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "@/components/ui/icons";
import { RecordDrawer } from "@/components/record/record-drawer";
import { RecordActivity } from "@/components/record/record-activity";
import { RecordProperties } from "@/components/record/record-properties";
import { RecordRelations } from "@/components/record/record-relations";
import { RecordSections } from "@/components/record/record-sections";
import type { RecordActivityEvent, RecordPropertyGroup, RecordRelation } from "@/components/record/record-types";
import { dispatchApi, type DispatchCampaign } from "@/lib/dispatch-api";
import { CHANNEL_LABEL, ITEM_STATUS_LABEL, PURPOSE_LABEL, CAMPAIGN_STATUS_LABEL } from "./dispatch-types";
import { MAX_ITEMS_PREVIEW, readableDate } from "./dispatch-utils";

type DispatchItem = {
  id: string;
  status: string;
  attempt?: number | null;
  updated_at?: string | null;
  last_error?: string | null;
};
function ItemList({ items, loading }: { items: DispatchItem[]; loading: boolean }) {
  const [page, setPage] = useState(0);
  const rows = items.slice(page * 25, (page + 1) * 25);
  return <section aria-label="Itens registrados" className="space-y-3">
    <p role="note" className="flex gap-2 rounded-[var(--radius-md)] bg-[var(--color-panel)] p-3 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">
      <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
      Até {MAX_ITEMS_PREVIEW} itens recentes. Este recorte não comprova a situação de toda a audiência. Identificadores de pessoas e erros brutos permanecem ocultos.
    </p>
    {loading ? <p role="status" className="py-3 text-xs text-[var(--color-muted)]">Carregando itens…</p> : <>
      {rows.length ? <div role="region" aria-label="Tabela de itens" tabIndex={0} className="overflow-x-auto">
        <table className="w-full min-w-[410px] text-left text-[length:var(--type-caption)]">
          <thead className="bg-[var(--color-panel)]"><tr>
            <th scope="col" className="px-2 py-2">Item</th><th scope="col" className="px-2 py-2">Estado</th>
            <th scope="col" className="px-2 py-2">Tentativas</th><th scope="col" className="px-2 py-2">Atualizado</th>
          </tr></thead>
          <tbody>{rows.map(item => <tr key={item.id} className="border-b border-[var(--color-border-subtle)]">
            <td className="px-2 py-3 font-mono">{item.id.slice(0, 8)}…</td>
            <td className="px-2 py-3">
              {ITEM_STATUS_LABEL[item.status] || "Estado desconhecido"}
              {!!item.last_error && <span className="block text-[length:var(--type-overline)] text-[var(--color-red)]">Falha registrada; detalhes não exibidos</span>}
            </td>
            <td className="px-2 py-3 tabular-nums">{item.attempt ?? "—"}</td>
            <td className="px-2 py-3">{readableDate(item.updated_at)}</td>
          </tr>)}</tbody>
        </table>
      </div> : <p className="py-4 text-xs text-[var(--color-muted)]">Nenhum item retornado pelo servidor.</p>}
      {items.length > 25 && <div className="flex items-center justify-end gap-3 text-[length:var(--type-caption)]">
        <button type="button" disabled={page === 0} onClick={() => setPage(i => i - 1)} className="disabled:opacity-40">Anterior</button>
        <span>{page + 1} de {Math.ceil(items.length / 25)}</span>
        <button type="button" disabled={(page + 1) * 25 >= items.length} onClick={() => setPage(i => i + 1)} className="disabled:opacity-40">Próxima</button>
      </div>}
    </>}
  </section>;
}
function CampaignReplies({ tenantId, userId, campaignId }: { tenantId: string; userId: string; campaignId: string }) {
  // Mounts only when the Replies tab opens; no request for hidden tab data.
  const replies = useQuery({
    queryKey: ["dispatch", "campaign-replies", tenantId, userId, campaignId],
    queryFn: () => dispatchApi.replies(campaignId),
    enabled: Boolean(tenantId && userId),
    staleTime: 15_000,
    retry: false,
  });
  const events: RecordActivityEvent[] = (replies.data?.items || []).map((reply, index) => ({
    id: campaignId + ":reply:" + index,
    kind: "contact",
    at: reply.occurred_at || null,
    title: reply.event_kind === "reply" ? "Resposta registrada" : "Evento recebido: " + reply.event_kind,
    origin: "Dispatch / evento recebido",
    status: reply.reply_intent || "Intenção não classificada",
    // Intentionally excludes provider payload, message contents, raw names, and internal notes.
  }));
  if (replies.isLoading) return <p role="status" className="p-4 text-xs text-[var(--color-muted)]">Consultando respostas…</p>;
  if (replies.isError) return <p role="alert" className="p-4 text-xs text-[var(--color-red)]">
    Respostas indisponíveis. <button type="button" className="underline" onClick={() => void replies.refetch()}>Tentar novamente</button>
  </p>;
  return <>
    <RecordActivity events={events} emptyMessage="Nenhuma resposta registrada pela origem consultada." />
    <p className="mt-3 text-[length:var(--type-caption)] text-[var(--color-muted)]">Resposta não comprova entrega, acordo, pagamento ou permanência.</p>
  </>;
}
export function CampaignDetailDrawer({
  campaign, tenantId, userId, onClose, onOpenMonitor,
}: {
  campaign: DispatchCampaign;
  tenantId: string;
  userId: string;
  onClose: () => void;
  onOpenMonitor: () => void;
}) {
  const detail = useQuery({
    queryKey: ["dispatch", "campaign-detail", tenantId, userId, campaign.id],
    queryFn: () => dispatchApi.detail(campaign.id),
    enabled: Boolean(tenantId && userId),
    staleTime: 15_000,
    retry: false,
  });
  const current = detail.data?.campaign || campaign;
  const items: DispatchItem[] = detail.data?.items || [];
  const status = CAMPAIGN_STATUS_LABEL[current.status] || current.status;
  const groups: RecordPropertyGroup[] = [
    { id: "identity", title: "Operação", properties: [
      { key: "id", label: "Identificador", value: current.id },
      { key: "purpose", label: "Finalidade", value: PURPOSE_LABEL[current.purpose] },
      { key: "channel", label: "Canal", value: CHANNEL_LABEL[current.channel] },
      { key: "status", label: "Estado", value: status, type: "status" },
      { key: "mode", label: "Modalidade", value: current.delivery_mode },
      { key: "source_kind", label: "Origem", value: current.source_kind },
      { key: "source_ref", label: "Referência da origem", value: current.source_ref },
      { key: "template", label: "Modelo", value: current.template_ref },
    ] },
    { id: "tracking", title: "Evidências de processamento", properties: [
      { key: "total", label: "Itens conhecidos", value: campaign.total, type: "number" },
      { key: "pending", label: "Pendentes", value: campaign.pending, type: "number" },
      { key: "accepted", label: "Pós-envio agregado*", value: campaign.accepted, type: "number" },
      { key: "problems", label: "Problemas", value: campaign.problems, type: "number" },
      { key: "created", label: "Criada em", value: readableDate(current.created_at) },
      { key: "approved", label: "Aprovada em", value: current.approved_at ? readableDate(current.approved_at) : null },
      { key: "scheduled", label: "Agendada para", value: current.scheduled_for ? readableDate(current.scheduled_for) : null },
    ] },
  ];
  const events: RecordActivityEvent[] = [
    ...(current.created_at ? [{ id: current.id + ":created", kind: "status" as const,
      title: "Campanha criada", at: current.created_at, origin: "Dispatch", status: "Rascunho registrado" }] : []),
    ...(current.approved_at ? [{ id: current.id + ":approved", kind: "status" as const,
      title: "Aprovação registrada", at: current.approved_at, origin: "Dispatch", status: "Aprovada" }] : []),
  ];
  const relations: RecordRelation[] = current.origin_proposal_id
    ? [{ id: current.id + ":proposal", label: "Proposta de origem", value: current.origin_proposal_id, type: "proposta" }]
    : [];
  return <RecordDrawer
    record={{ kind: "campaign", id: current.id, title: current.name,
      subtitle: PURPOSE_LABEL[current.purpose] + " · " + CHANNEL_LABEL[current.channel],
      caption: "Campanha operacional de Dispatch" }}
    onClose={onClose}
    status={<span className="mira-tag mira-tag--blue">{status}</span>}
    actions={[
      { id: "workflows", label: "Ver Workflows", href: "/workflows" },
      { id: "queue", label: "Ver fila", primary: true,
        onClick: () => { onClose(); onOpenMonitor(); } },
    ]}
  >
    {detail.isLoading && <p role="status" className="p-4 text-xs text-[var(--color-muted)]">Carregando dados da campanha…</p>}
    {detail.isError && <p role="alert" className="p-4 text-xs text-[var(--color-red)]">
      Não foi possível consultar os detalhes. <button type="button" className="underline" onClick={() => void detail.refetch()}>Tentar novamente</button>
    </p>}
    {!detail.isError && <RecordSections sections={[
      { id: "properties", label: "Propriedades", content: <>
        <RecordProperties groups={groups} compact />
        <p className="mt-3 text-[length:var(--type-caption)] text-[var(--color-muted)]">* Inclui aceito, entregue, lido e respondido. Não comprova entrega individual.</p>
      </> },
      { id: "items", label: "Itens", content: <ItemList items={items} loading={detail.isLoading} /> },
      { id: "activity", label: "Atividade", content: <RecordActivity events={events}
        emptyMessage="Nenhuma atividade adicional comprovada nesta fonte." /> },
      { id: "replies", label: "Respostas", content: <CampaignReplies
        tenantId={tenantId} userId={userId} campaignId={campaign.id} /> },
      { id: "relations", label: "Relações", content: <RecordRelations relations={relations} /> },
    ]} />}
  </RecordDrawer>;
}
