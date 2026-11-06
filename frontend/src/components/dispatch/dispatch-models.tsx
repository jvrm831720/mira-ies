"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { ArrowRight, Search, ShieldCheck } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { hasNavigationPermission, getVisibleNavigation } from "@/components/layout/navigation";
import { dispatchApi, type DispatchTemplate } from "@/lib/dispatch-api";
import { CHANNEL_LABEL, PURPOSE_LABEL } from "./dispatch-types";
import { readableDate } from "./dispatch-utils";

export function DispatchModels() {
  const [purpose,setPurpose]=useState("");
  const [channel,setChannel]=useState("");
  const [status,setStatus]=useState("");
  const [search,setSearch]=useState("");
  const [selected,setSelected]=useState<DispatchTemplate|null>(null);
  const me=useQuery({queryKey:["org-me"],queryFn:api.me,staleTime:60_000,retry:false});
  const allowed=hasNavigationPermission(me.data,"campaigns.view")
    && getVisibleNavigation(me.data).some(group=>group.items.some(item=>item.href==="/disparos"));
  const canCreate=hasNavigationPermission(me.data,"campaigns.create");
  const templates=useQuery({
    queryKey:["dispatch","templates",me.data?.tenant_id,me.data?.user_id],
    queryFn:dispatchApi.templates,enabled:allowed,
    staleTime:30_000,retry:false,
  });
  const records=useMemo(()=>(templates.data?.items||[]).filter(item=>
    (!purpose||item.purpose===purpose)&&(!channel||item.channel===channel)&&(!status||item.status===status)
    &&(!search||[item.code,item.subject].some(v=>v.toLocaleLowerCase("pt-BR").includes(search.trim().toLocaleLowerCase("pt-BR"))))),
    [templates.data,purpose,channel,status,search]);
  if(me.isLoading)return <main className="mira-page p-8 text-[12px]" role="status">Verificando permissões…</main>;
  if(!allowed)return <main className="mira-page p-8 text-[12px]" role="alert">Sem permissão para visualizar modelos neste workspace.</main>;
  return <>
    <Header title="Modelos de comunicação" subtitle="Biblioteca de mensagens reutilizáveis por finalidade e canal"/>
    <main className="mira-page mx-auto max-w-[1350px] space-y-5 px-4 py-5 md:px-7">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">MIRA Operação / Modelos</p>
          <h1 className="mt-1 text-[18px] font-semibold">Biblioteca de mensagens</h1>
          <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Modelo criado, aprovado e utilizável são estados distintos.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/disparos" className="rounded-md border border-[var(--color-border)] px-3 py-2 text-[12px]">Voltar à operação</Link>
          {canCreate && <Link href="/disparos/modelos/gerenciar" className="inline-flex items-center gap-1 rounded-md bg-[var(--color-ink)] px-3 py-2 text-[12px] font-medium text-white">Gerenciar modelos <ArrowRight className="h-3 w-3"/></Link>}
        </div>
      </div>
      <section className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] p-3">
          <label className="relative flex min-w-[175px] flex-1 items-center sm:max-w-[320px]">
            <Search className="absolute left-2 h-4 w-4 text-[var(--color-muted)]"/>
            <input aria-label="Buscar modelos" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar modelos…"
              className="h-9 w-full rounded-md border border-[var(--color-border)] pl-8 pr-2 text-[12px]"/>
          </label>
          <select aria-label="Filtrar finalidade" value={purpose} onChange={e=>setPurpose(e.target.value)} className="h-9 rounded-md border border-[var(--color-border)] px-2 text-[12px]">
            <option value="">Todas as finalidades</option>
            {Object.entries(PURPOSE_LABEL).map(([key,label])=><option value={key} key={key}>{label}</option>)}
          </select>
          <select aria-label="Filtrar canal" value={channel} onChange={e=>setChannel(e.target.value)} className="h-9 rounded-md border border-[var(--color-border)] px-2 text-[12px]">
            <option value="">Todos os canais</option>
            {Object.entries(CHANNEL_LABEL).map(([key,label])=><option value={key} key={key}>{label}</option>)}
          </select>
          <select aria-label="Filtrar estado" value={status} onChange={e=>setStatus(e.target.value)} className="h-9 rounded-md border border-[var(--color-border)] px-2 text-[12px]">
            <option value="">Todos os estados</option><option value="draft">Rascunho</option>
            <option value="approved">Aprovado</option><option value="retired">Arquivado</option>
          </select>
        </div>
        {templates.isError&&<p role="alert" className="p-4 text-[12px] text-[var(--color-red)]">Não foi possível carregar os modelos.</p>}
        {templates.isLoading&&<p role="status" className="p-6 text-[12px] text-[var(--color-muted)]">Carregando biblioteca…</p>}
        {!templates.isLoading&&!templates.isError&&<div className="overflow-x-auto">
          <table className="w-full min-w-[580px] text-left text-[12px]">
            <thead className="bg-[var(--color-panel)] text-[11px] text-[var(--color-slate-600)]">
              <tr><th scope="col" className="px-4 py-3">Modelo</th><th scope="col" className="px-4 py-3">Finalidade</th>
                <th scope="col" className="px-4 py-3">Canal</th><th scope="col" className="px-4 py-3">Estado</th>
                <th scope="col" className="px-4 py-3">Aprovação</th></tr>
            </thead>
            <tbody>{records.map(item=><tr key={item.id} className="border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-panel)]">
              <td className="px-4 py-3"><button type="button" onClick={()=>setSelected(item)} className="text-left font-semibold text-[var(--color-ink)] hover:text-[var(--color-blue)]">
                {item.code}<span className="ml-2 text-[10px] font-normal text-[var(--color-muted)]">v{item.version}</span>
              </button></td><td className="px-4 py-3">{PURPOSE_LABEL[item.purpose]}</td>
              <td className="px-4 py-3">{CHANNEL_LABEL[item.channel]}</td>
              <td className="px-4 py-3"><span className="mira-tag mira-tag--blue">{item.status==="approved"?"Aprovado":item.status==="draft"?"Rascunho":"Arquivado"}</span></td>
              <td className="px-4 py-3">{readableDate(item.approved_at)}</td>
            </tr>)}</tbody>
          </table>
          {!records.length&&<p className="p-6 text-center text-[12px] text-[var(--color-muted)]">Nenhum modelo neste recorte.</p>}
        </div>}
      </section>
      {selected&&<section aria-label="Prévia do modelo" className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5">
        <div className="flex justify-between gap-2"><h2 className="text-[13px] font-semibold">{selected.code} · versão {selected.version}</h2>
          <button type="button" onClick={()=>setSelected(null)} className="text-[12px] text-[var(--color-blue)]">Fechar</button></div>
        <p className="mt-2 text-[11px] text-[var(--color-muted)]">Prévia estática: variáveis não são preenchidas com dados reais de pessoas.</p>
        {selected.subject&&<p className="mt-3 text-[12px] font-semibold">{selected.subject}</p>}
        <p className="mt-2 whitespace-pre-wrap break-words text-[12px]">{selected.body}</p>
      </section>}
      <p className="flex items-start gap-2 text-[11px] text-[var(--color-muted)]"><ShieldCheck className="h-4 w-4"/>A aprovação de modelos depende de autorização humana existente; não é executada por esta biblioteca.</p>
    </main>
  </>;
}
