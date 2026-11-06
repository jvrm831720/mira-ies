"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { api } from "@/lib/api";
import {
  collectionsApi, type CollectionCase, type CollectionCaseDetail,
} from "@/lib/collections-api";

const statuses = [
  { value: "", label: "Todos os estados" },
  { value: "open", label: "Aberta" },
  { value: "agreement", label: "Em acordo" },
  { value: "paid", label: "Paga (origem)" },
  { value: "disputed", label: "Contestada" },
  { value: "cancelled", label: "Cancelada" },
  { value: "unknown", label: "Não determinada" },
] as const;

const labels: Record<string, string> = {
  open: "Aberta", agreement: "Em acordo", paid: "Paga (origem)",
  disputed: "Contestada", cancelled: "Cancelada", unknown: "Desconhecida",
};

function Currency({ value }: { value: string | null }) {
  if (value === null) return <span className="text-[#9299A4]">Não informado</span>;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return <span>{value}</span>;
  return <span className="tabular-nums">{new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(amount)}</span>;
}

function Time({ value }: { value: string | null }) {
  if (!value) return <span className="text-[#9299A4]">Sem registro</span>;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <span>{value}</span>;
  return <time dateTime={value}>{new Intl.DateTimeFormat("pt-BR", {dateStyle:"short",timeStyle:"short"}).format(date)}</time>;
}

function CaseDetail({ record, loading, error, onClose }: {
  record: CollectionCaseDetail | undefined;
  loading: boolean;
  error: boolean;
  onClose: () => void;
}) {
  return <aside aria-label="Detalhes do caso" className="rounded-xl border border-[#E6E7EA] bg-white p-5 lg:sticky lg:top-6 lg:self-start">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold">Caso financeiro</h2>
      <button type="button" onClick={onClose} className="rounded-md border px-2 py-1 text-xs hover:bg-[#F8F9FA]">Fechar</button>
    </div>
    {loading && <p role="status" className="mt-5 text-xs text-[#667085]">Carregando detalhes…</p>}
    {error && <p role="alert" className="mt-5 text-xs text-[#B42318]">Não foi possível consultar este caso.</p>}
    {record && <>
      <dl className="mt-5 space-y-3 text-xs">
        {([
          ["Referência", record.case.external_ref],
          ["Estado da fonte", labels[record.case.status] ?? record.case.status],
          ["Identificador relacionado", record.case.subject_ref],
          ["Origem", record.case.source],
          ["Versão da origem", String(record.case.source_version)],
          ["Evidência", record.case.evidence_ref],
        ] as const).map(([label, value]) => <div key={label} className="grid grid-cols-[110px_1fr] gap-2 border-b border-[#F0F1F3] pb-2">
          <dt className="text-[#858C96]">{label}</dt><dd className="break-all text-[#101112]">{value}</dd>
        </div>)}
        <div className="flex justify-between gap-2"><dt className="text-[#858C96]">Saldo informado</dt><dd><Currency value={record.case.balance}/></dd></div>
        <div className="flex justify-between gap-2"><dt className="text-[#858C96]">Verificado em</dt><dd><Time value={record.case.verified_at}/></dd></div>
      </dl>
      <h3 className="mb-2 mt-7 text-xs font-semibold">Eventos financeiros confirmados pela origem</h3>
      {record.payment_events.length === 0
        ? <p className="rounded-lg bg-[#F8F9FA] p-3 text-xs text-[#667085]">Nenhum evento financeiro confirmado nesta consulta.</p>
        : <ol className="space-y-2">{record.payment_events.map(event=><li key={event.id} className="rounded-lg border border-[#E6E7EA] p-3 text-xs">
          <div className="flex justify-between gap-3"><strong><Currency value={event.amount_paid}/></strong><Time value={event.paid_at}/></div>
          <p className="mt-1 text-[#667085]">Fonte: {event.source} · {event.obligation_status}</p>
          <p className="mt-1 text-[#667085]">Saldo após evento: <Currency value={event.remaining_balance}/></p>
        </li>)}</ol>}
      {record.payment_events_limited && <p className="mt-2 text-xs text-[#946200]">Somente os 100 eventos mais recentes são apresentados.</p>}
      <p className="mt-5 border-t pt-3 text-[11px] text-[#858C96]">Registros de origem não são comprovantes bancários nem garantem conciliação externa.</p>
    </>}
  </aside>;
}

export function CollectionsExperience() {
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const me = useQuery({queryKey:["org-me"],queryFn:api.me,retry:false,staleTime:60_000});
  const profile=me.data?.operation_profile;
  const educationWithBilling = profile === "institution"
    && Array.isArray(me.data?.enabled_modules) && me.data.enabled_modules.includes("billing");
  const allowedProfile = ["collection", "debt_collection", "billing", "cobranca"].includes(profile ?? "") || educationWithBilling;
  const allowed = allowedProfile && hasNavigationPermission(me.data,"audit.view")
    && (!Array.isArray(me.data?.enabled_modules) || me.data.enabled_modules.includes("billing"));
  const tenant = me.data?.tenant_id ?? "";
  const user = me.data?.user_id ?? "";
  const cases = useQuery({
    queryKey:["collections","cases",tenant,user,applied,status,offset],
    queryFn:()=>collectionsApi.cases({q:applied,status,offset}),
    enabled:allowed && !!tenant,retry:false,staleTime:20_000,
  });
  const detail = useQuery({
    queryKey:["collections","detail",tenant,user,selectedId],
    queryFn:()=>collectionsApi.detail(selectedId!),
    enabled:allowed && !!selectedId && !!tenant,retry:false,staleTime:20_000,
  });
  useEffect(()=>{setSelectedId(null);setOffset(0);setApplied("");setSearch("");setStatus("");},[tenant,user]);
  if (me.isLoading) return <main className="mira-page p-7 text-xs text-[#667085]" role="status">Verificando acesso…</main>;
  if (me.isError || !allowed) return <main className="mira-page p-7 text-sm text-[#667085]" role="alert">A área de cobrança não está disponível para este workspace ou cargo.</main>;
  const rows: CollectionCase[]=cases.data?.items ?? [];
  return <main className="mira-page space-y-5 p-5 md:p-7">
    <Header title="Cobrança" subtitle="Casos e obrigações informadas por fontes verificadas" />
    <div className="rounded-xl border border-[#E6E7EA] bg-[#F8F9FA] px-4 py-3 text-xs text-[#667085]">Esta é uma visualização de consulta. Criar acordos, alterar dívidas e cobrar clientes não está habilitado aqui.</div>
    <form className="flex flex-wrap items-center gap-2" onSubmit={e=>{e.preventDefault();setApplied(search);setOffset(0);}}>
      <label className="sr-only" htmlFor="collections-search">Buscar referência</label>
      <input id="collections-search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar referência ou identificador" maxLength={160} className="min-w-[220px] flex-1 rounded-lg border border-[#E6E7EA] bg-white px-3 py-2 text-xs outline-offset-2 focus:outline-[#266DF0]"/>
      <label className="sr-only" htmlFor="collections-status">Filtrar estado</label>
      <select id="collections-status" value={status} onChange={e=>{setStatus(e.target.value);setOffset(0);}} className="rounded-lg border border-[#E6E7EA] bg-white px-3 py-2 text-xs">
        {statuses.map(s=><option key={s.value} value={s.value}>{s.label}</option>)}
      </select>
      <button type="submit" className="rounded-lg bg-[#101112] px-4 py-2 text-xs font-medium text-white hover:bg-[#343637]">Buscar</button>
    </form>
    <div className={"grid items-start gap-4 "+(selectedId?"lg:grid-cols-[minmax(0,1fr)_340px]":"")}>
      <section className="overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
        <header className="flex items-center justify-between gap-2 border-b border-[#E6E7EA] px-4 py-3">
          <h2 className="text-xs font-semibold">Casos</h2>
          <span className="text-xs text-[#667085]">{cases.data?cases.data.total.toLocaleString("pt-BR")+" encontrados":"Contagem indisponível"}</span>
        </header>
        {cases.isLoading && <p role="status" className="p-6 text-xs text-[#667085]">Consultando casos…</p>}
        {cases.isError && <div role="alert" className="p-6 text-xs text-[#B42318]">Falha ao consultar casos. <button type="button" className="underline" onClick={()=>void cases.refetch()}>Tentar novamente</button></div>}
        {cases.isSuccess && rows.length===0 && <p className="p-8 text-center text-xs text-[#667085]">Nenhum caso corresponde aos filtros atuais.</p>}
        {rows.length>0 && <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-xs">
          <thead className="bg-[#F8F9FA] text-[#727A84]"><tr>{["Referência","Estado","Saldo informado","Origem","Atualização"].map(label=><th key={label} scope="col" className="px-4 py-3 font-medium">{label}</th>)}</tr></thead>
          <tbody>{rows.map(row=><tr key={row.id} className="border-t border-[#F0F1F3] hover:bg-[#FAFBFC]">
            <td className="px-4 py-3"><button type="button" onClick={()=>setSelectedId(row.id)} className="font-medium text-[#266DF0] hover:underline">{row.external_ref}</button></td>
            <td className="px-4 py-3">{labels[row.status]??row.status}</td>
            <td className="px-4 py-3"><Currency value={row.balance}/></td>
            <td className="px-4 py-3">{row.source}</td>
            <td className="px-4 py-3"><Time value={row.updated_at}/></td>
          </tr>)}</tbody>
        </table></div>}
        {cases.data && cases.data.total>25 && <footer className="flex items-center justify-between border-t px-4 py-3 text-xs">
          <span>{offset+1}–{offset+rows.length} de {cases.data.total}</span>
          <div className="flex gap-2">
            <button type="button" disabled={offset===0} onClick={()=>{setOffset(Math.max(0,offset-25));setSelectedId(null);}} className="rounded border px-3 py-1.5 disabled:opacity-30">Anterior</button>
            <button type="button" disabled={!cases.data.has_more} onClick={()=>{setOffset(offset+25);setSelectedId(null);}} className="rounded border px-3 py-1.5 disabled:opacity-30">Próxima</button>
          </div>
        </footer>}
      </section>
      {selectedId && <CaseDetail record={detail.data} loading={detail.isLoading} error={detail.isError} onClose={()=>setSelectedId(null)}/>}
    </div>
  </main>;
}
