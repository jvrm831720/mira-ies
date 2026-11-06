"use client";
import { useMemo, useState } from "react";
import { Search, X } from "@/components/ui/icons";
import { ObjectDataTable } from "@/components/object-index/object-data-table";
import type { ObjectField, ObjectSort } from "@/components/object-index/object-index-types";
import type { DispatchCampaign } from "@/lib/dispatch-api";
import { CAMPAIGN_STATUS_LABEL, CHANNEL_LABEL, PURPOSE_LABEL } from "./dispatch-types";
import { MAX_CAMPAIGN_PREVIEW, readableDate } from "./dispatch-utils";

const fields: ObjectField<DispatchCampaign>[] = [
  { key: "name", title: "Campanha", type: "text", primary: true, width: 300, sortable: true,
    getValue: item => item.name },
  { key: "status", title: "Estado", type: "status", width: 135, sortable: true,
    getValue: item => item.status,
    render: item => <span className="mira-tag mira-tag--blue">{CAMPAIGN_STATUS_LABEL[item.status] || item.status}</span> },
  { key: "purpose", title: "Finalidade", type: "text", width: 150, sortable: true,
    getValue: item => PURPOSE_LABEL[item.purpose] },
  { key: "channel", title: "Canal", type: "text", width: 110, sortable: true,
    getValue: item => CHANNEL_LABEL[item.channel] },
  { key: "total", title: "Itens", type: "number", width: 75, sortable: true,
    getValue: item => item.total },
  { key: "pending", title: "Pendentes", type: "number", width: 100, sortable: true,
    getValue: item => item.pending },
  { key: "accepted", title: "Pós-envio*", type: "number", width: 95, sortable: true,
    getValue: item => item.accepted },
  { key: "problems", title: "Problemas", type: "number", width: 95, sortable: true,
    getValue: item => item.problems },
  { key: "created_at", title: "Criada em", type: "datetime", width: 160, sortable: true,
    getValue: item => item.created_at, render: item => readableDate(item.created_at) },
];

type Tab = "all" | DispatchCampaign["status"] | "problems";
const tabs: Array<{id:Tab;name:string}> = [
  {id:"all",name:"Todas"},{id:"draft",name:"Rascunhos"},{id:"approved",name:"Aprovadas"},
  {id:"scheduled",name:"Agendadas"},{id:"running",name:"Em execução"},
  {id:"completed",name:"Concluídas"},{id:"problems",name:"Com problemas"},
];
export function CampaignIndex({
  campaigns, loading, error, onOpen, onRetry,
}: {
  campaigns: DispatchCampaign[];
  loading: boolean;
  error: boolean;
  onOpen: (campaign: DispatchCampaign) => void;
  onRetry: () => void;
}) {
  const [tab, setTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<ObjectSort | null>({ key: "created_at", desc: true });
  const [visible, setVisible] = useState(fields.map(field => field.key));
  const [selected, setSelected] = useState<Record<string,boolean>>({});
  const [showColumns, setShowColumns] = useState(false);
  const filtered = useMemo(() => campaigns.filter(item => {
    const relevant = tab === "all" || (tab === "problems" ? item.problems > 0 : item.status === tab);
    const q = search.trim().toLocaleLowerCase("pt-BR");
    return relevant && (!q || [item.name, item.purpose, item.channel, item.status].some(v => v.toLocaleLowerCase("pt-BR").includes(q)));
  }), [campaigns,tab,search]);
  const selectedRow = filtered.find(item => selected[item.id]);
  return <section className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
    <div className="border-b border-[var(--color-border)] px-5 py-4">
      <h2 className="text-[13px] font-semibold">Campanhas de Dispatch</h2>
      <p className="mt-1 text-[11px] text-[var(--color-muted)]">Objetos operacionais. Propostas de permanência possuem ciclo de aprovação separado e vínculo explícito.</p>
    </div>
    <div className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)] px-3">
      {tabs.map(t => <button type="button" key={t.id} aria-current={tab === t.id ? "page" : undefined}
        className={"shrink-0 border-b-2 px-3 py-3 text-[12px] " + (tab===t.id ? "border-[var(--color-ink)] font-semibold" : "border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-ink)]")}
        onClick={() => {setTab(t.id);setSelected({});}}>{t.name}</button>)}
    </div>
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-4 py-2.5">
      <label className="relative flex min-w-[210px] max-w-[320px] flex-1 items-center">
        <Search className="absolute left-2.5 h-3.5 w-3.5 text-[var(--color-muted)]" aria-hidden="true"/>
        <input aria-label="Buscar campanhas nesta prévia" className="h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] py-2 pl-8 pr-3 text-[12px] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"
          value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar na prévia…" />
      </label>
      <div className="relative">
        <button type="button" aria-expanded={showColumns} onClick={()=>setShowColumns(v=>!v)}
          className="h-9 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[12px] hover:bg-[var(--color-panel)]">Propriedades</button>
        {showColumns && <div className="absolute right-0 top-10 z-20 w-[215px] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-3 shadow-[var(--shadow-overlay)]">
          {fields.map(field => <label className="flex items-center gap-2 py-1.5 text-[12px]" key={field.key}>
            <input type="checkbox" disabled={field.primary} checked={field.primary || visible.includes(field.key)}
              onChange={e=>setVisible(prev=>e.target.checked?[...prev,field.key]:prev.filter(key=>key!==field.key))}/>{field.title}
          </label>)}
          <button className="mt-2 text-[11px] text-[var(--color-blue)]" type="button" onClick={()=>setShowColumns(false)}>Fechar</button>
        </div>}
      </div>
      <span className="ml-auto text-[11px] tabular-nums text-[var(--color-muted)]">{filtered.length} na prévia</span>
    </div>
    {campaigns.length >= MAX_CAMPAIGN_PREVIEW && <p role="note" className="border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[11px] text-[var(--color-slate-600)]">
      A API devolve até 100 campanhas recentes, sem paginação. Filtros, ordenação e seleção atuam somente sobre essa amostra.
    </p>}
    {error ? <p role="alert" className="p-6 text-[12px] text-[var(--color-red)]">Não foi possível consultar campanhas. <button type="button" onClick={onRetry} className="underline">Tentar novamente</button></p>
      : <ObjectDataTable records={filtered} fields={fields} visible={visible} onVisibleChange={setVisible}
        sort={sort} onSortChange={setSort} selected={selected} onSelectedChange={setSelected}
        onOpen={onOpen} loading={loading} emptyText="Nenhuma campanha encontrada neste recorte." />}
    <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] px-4 py-3 text-[11px] text-[var(--color-muted)]">
      <span>* Pós-envio = aceito + entregue + lido + respondido. Não comprova entrega.</span>
      {selectedRow && <button type="button" onClick={()=>onOpen(selectedRow)} className="inline-flex items-center gap-1 text-[var(--color-blue)]">Abrir seleção <X className="h-3 w-3 rotate-45" /></button>}
    </footer>
  </section>;
}
