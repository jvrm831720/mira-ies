"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { ArrowRight, Check, Info, Plus, RefreshCw, Search, X } from "@/components/ui/icons";
import { filterAppsCatalog, normalizeAppKey, unifyAppsCatalog, type AppsCategory, type CatalogApp } from "./apps-catalog-model";

type Tab = "Mais usados" | "Conectados" | "Descobrir";
const categories: Array<"Todos" | AppsCategory> = ["Todos", "Comunicação", "CRM e relacionamento", "Documentos e arquivos", "Dados e análise", "Atendimento e suporte", "Agenda e agendamento", "Marketing institucional", "Acadêmico", "Financeiro", "Produtividade", "IA", "Outros"];
const brandLogos:Record<string,string> = {
 whatsapp:"/apps/whatsapp.svg",gmail:"/apps/gmail.svg",googlecalendar:"/apps/googlecalendar.svg",
 googledrive:"/apps/googledrive.svg",moodle:"/apps/moodle.svg",canvas:"/apps/canvas.svg",
 googlesheets:"/apps/googlesheets.svg",zapier:"/apps/zapier.svg",
};
const tone:Record<string,string> = {
 green:"bg-[var(--mira-apps-green)] text-[var(--mira-apps-white)]",
 red:"bg-[var(--mira-apps-red)] text-[var(--mira-apps-white)]",
 blue:"bg-[var(--mira-apps-blue)] text-[var(--mira-apps-white)]",
 orange:"bg-[var(--mira-apps-orange)] text-[var(--mira-apps-white)]",
 purple:"bg-[var(--mira-apps-purple)] text-[var(--mira-apps-white)]",
 cyan:"bg-[var(--mira-apps-cyan)] text-[var(--mira-apps-dark)]",
 gray:"bg-[var(--mira-apps-icon-gray)] text-[var(--mira-apps-white)]",
};
function State({ item }: { item: CatalogApp }) {
 const isConnected=item.status==="connected"||item.status==="configured";
 return <span className={"inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs leading-none " +
  (isConnected?"border-[var(--mira-apps-ok-border)] bg-[var(--mira-apps-ok-bg)] text-[var(--mira-apps-ok)]":
   item.status==="error"?"border-[var(--mira-apps-warn-border)] text-[var(--mira-apps-warn)]":
   "border-[var(--mira-apps-border)] bg-[var(--mira-apps-chip)] text-[var(--mira-apps-muted)]")}>
  {isConnected ? <Check size={13} aria-hidden="true"/> : item.status==="error" ? <Info size={13} aria-hidden="true"/> : null}
  {item.statusText}
 </span>;
}
export function AppsCatalogExperience() {
 const [tab,setTab]=useState<Tab>("Mais usados");
 const [category,setCategory]=useState<(typeof categories)[number]>("Todos");
 const [query,setQuery]=useState("");
 const [limit,setLimit]=useState(32);
 const [selected,setSelected]=useState<CatalogApp|null>(null);
 const [requestOpen,setRequestOpen]=useState(false);
 const [connecting,setConnecting]=useState(false);
 const [requestName,setRequestName]=useState("");
 const [requestGoal,setRequestGoal]=useState("");

 const me=useQuery({queryKey:["org-me"],queryFn:()=>api.me(),staleTime:60_000,retry:false});
 const canRead=hasNavigationPermission(me.data,"data.view");
 const canManage=hasNavigationPermission(me.data,"settings.manage");
 const tenant=me.data?.tenant_id;
 const nativeCatalog=useQuery({
  queryKey:["apps-catalog",tenant,"native"],
  queryFn:api.listConnectors,enabled:canRead,staleTime:300_000,retry:1,
 });
 const curatedCatalog=useQuery({
  queryKey:["apps-catalog",tenant,"curated"],
  queryFn:api.composioCuratedCategories,enabled:canRead,staleTime:300_000,retry:1,
 });
 const externalCatalog=useQuery({
  queryKey:["apps-catalog",tenant,"external"],
  queryFn:api.composioCatalog,enabled:canRead&&canManage,staleTime:300_000,retry:false,
 });
 const accounts=useQuery({
  queryKey:["apps-catalog",tenant,"accounts"],
  queryFn:api.composioConnections,enabled:canRead&&canManage,staleTime:60_000,retry:false,
 });
 const authOptions=useQuery({
  queryKey:["apps-catalog",tenant,"auth-options"],
  queryFn:api.composioOnboardingAuthOptions,enabled:canRead&&canManage,retry:false,
 });
 const jacad=useQuery({
  queryKey:["apps-catalog",tenant,"jacad"],
  queryFn:api.jacadConnection,enabled:canRead&&canManage,staleTime:60_000,retry:false,
 });
 const sponte=useQuery({
  queryKey:["apps-catalog",tenant,"sponte"],
  queryFn:api.sponteConnection,enabled:canRead&&canManage,staleTime:60_000,retry:false,
 });
 const curatedApps=useMemo(()=>curatedCatalog.data?.items.flatMap(group=>
  group.composio_toolkits.map(tool=>({
   slug:tool.slug,name:tool.name,description:group.name,
   mira_category_label:group.name,
  }))
 )||[],[curatedCatalog.data]);
 const rows=useMemo(()=>unifyAppsCatalog(
  nativeCatalog.data?.connectors||[],
  [...curatedApps,...(externalCatalog.data?.items||[])],
  accounts.data?.items||[],
  {jacad:jacad.data,sponte:sponte.data},
 ),[nativeCatalog.data,curatedApps,externalCatalog.data,accounts.data,jacad.data,sponte.data]);
 const visible=useMemo(()=>filterAppsCatalog(rows,query,category,tab),[rows,query,category,tab]);
 const shown=visible.slice(0,limit);
 const partial=canManage && externalCatalog.isError;
 const loading=(nativeCatalog.isLoading && !nativeCatalog.data) || (curatedCatalog.isLoading && !curatedCatalog.data);

 async function connectApp(item: CatalogApp) {
  if(connecting) return;
  const option=authOptions.data?.items.find(row=>normalizeAppKey(row.toolkit_slug)===normalizeAppKey(item.slug));
  if(!option){toast.error("Conexão indisponível: autenticação não configurada.");return;}
  setConnecting(true);
  try{
   const response=await api.startComposioOnboardingConnection({toolkit_slug:option.toolkit_slug,auth_config_id:option.auth_config_id});
   const target=new URL(response.redirect_url);
   if(target.protocol!=="https:" && !(process.env.NODE_ENV==="development" && target.hostname==="localhost" && target.protocol==="http:")){
    throw new Error("Endereço de autorização inválido.");
   }
   window.location.assign(target.toString());
  }catch(error){
   toast.error(error instanceof Error?error.message:"Não foi possível iniciar a conexão.");
   setConnecting(false);
  }
 }
 function refresh(){
  void nativeCatalog.refetch();void curatedCatalog.refetch();
  if(canManage){
   void authOptions.refetch();void externalCatalog.refetch();void accounts.refetch();void jacad.refetch();void sponte.refetch();
  }
 }
 async function copyRequest(){
  const app=requestName.trim(),goal=requestGoal.trim();
  if(!app){toast.error("Informe o nome da integração.");return;}
  const message=["Solicitação de integração à MIRA","Workspace: "+(me.data?.tenant_name||"Não informado"),"Aplicativo: "+app,"Objetivo: "+(goal||"Não informado")].join("\n");
  try{await navigator.clipboard.writeText(message);toast.success("Solicitação copiada. Envie-a ao suporte da MIRA.");setRequestOpen(false);}
  catch{toast.error("Não foi possível copiar. Selecione e copie o texto manualmente.");}
 }
 const tabs:Tab[]=["Mais usados","Conectados","Descobrir"];
 return <div className="mira-apps-page min-h-dvh bg-[var(--mira-apps-dark)] text-[var(--mira-apps-white)]">
  <header className="flex h-[58px] items-center justify-between border-b border-[var(--mira-apps-border)] px-6 md:px-8">
   <span className="text-sm font-medium">Apps e integrações</span>
   <button type="button" onClick={refresh} title="Atualizar catálogo" aria-label="Atualizar catálogo"
    className="rounded-lg p-2 text-[var(--mira-apps-muted)] hover:bg-[var(--mira-apps-hover)] hover:text-[var(--mira-apps-white)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-apps-blue)]">
    <RefreshCw size={16} aria-hidden="true"/>
   </button>
  </header>
  <main className="mx-auto max-w-[1680px] px-5 pb-16 pt-8 md:px-9">
   <div className="flex flex-wrap items-start justify-between gap-4">
    <div><h1 className="text-[length:var(--type-display-medium)] font-semibold tracking-tight">Apps e integrações</h1>
    <p className="mt-1 text-sm text-[var(--mira-apps-muted)]">Conecte a MIRA às ferramentas que sua operação já usa.</p></div>
    {canRead && <button type="button" onClick={()=>setRequestOpen(true)}
      className="inline-flex items-center gap-2 rounded-xl bg-[var(--mira-apps-blue)] px-4 py-2.5 text-sm font-semibold text-[var(--mira-apps-white)] hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--mira-apps-blue)]">
      <Plus size={17} aria-hidden="true"/> Solicitar integração
    </button>}
   </div>
   {me.isLoading ? <p role="status" className="mt-12 text-sm text-[var(--mira-apps-muted)]">Verificando permissões do workspace…</p>
   : me.isError || !canRead ? <div role="alert" className="mt-10 rounded-xl border border-[var(--mira-apps-border)] p-6 text-sm">Você não tem permissão para consultar apps e integrações neste workspace.</div>
   : <>
    <div role="tablist" aria-label="Explorar apps" className="mt-7 flex flex-wrap gap-2 border-b border-[var(--mira-apps-border)]">
     {tabs.map(value=><button key={value} role="tab" aria-selected={tab===value} onClick={()=>{setTab(value);setLimit(32);}}
       className={"relative min-h-11 rounded-t-lg px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-[var(--mira-apps-blue)] "+
         (tab===value?"bg-[var(--mira-apps-chip)] text-[var(--mira-apps-white)] after:absolute after:bottom-0 after:left-0 after:h-[2px] after:w-full after:bg-[var(--mira-apps-blue)]":"text-[var(--mira-apps-muted)] hover:text-[var(--mira-apps-white)]")}>{value}</button>)}
    </div>
    <div className="mt-6 flex flex-wrap items-center gap-2.5">
     <label className="relative min-w-[220px] flex-1 sm:max-w-[355px]">
      <span className="sr-only">Buscar apps</span>
      <Search className="absolute left-3 top-2.5 text-[var(--mira-apps-muted)]" size={17} aria-hidden="true"/>
      <input type="search" value={query} onChange={event=>{setQuery(event.target.value);setLimit(32);}} placeholder="Buscar apps"
       className="h-10 w-full rounded-xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-dark)] pl-10 pr-3 text-sm text-[var(--mira-apps-white)] placeholder:text-[var(--mira-apps-muted)] focus:border-[var(--mira-apps-blue)] focus:outline-none"/>
     </label>
     <div role="group" aria-label="Filtrar por categoria" className="flex flex-wrap gap-2">
      {categories.map(value=><button key={value} type="button" aria-pressed={category===value} onClick={()=>{setCategory(value);setLimit(32);}}
       className={"rounded-full border px-3 py-2 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-apps-blue)] "+
        (category===value?"border-[var(--mira-apps-blue)] bg-[var(--mira-apps-blue-soft)] text-[var(--mira-apps-blue-light)]":"border-[var(--mira-apps-border)] text-[var(--mira-apps-muted)] hover:border-[var(--mira-apps-muted)] hover:text-[var(--mira-apps-white)]")}>{value}</button>)}
     </div>
     <span className="ml-auto rounded-full bg-[var(--mira-apps-chip)] px-3 py-2 text-xs text-[var(--mira-apps-muted)]">{rows.length} no catálogo</span>
    </div>
    {partial && <p role="status" className="mt-5 rounded-lg border border-[var(--mira-apps-border)] p-3 text-xs text-[var(--mira-apps-muted)]">
      O catálogo ao vivo está temporariamente indisponível. As ferramentas conhecidas da MIRA continuam visíveis, mas podem exigir configuração para conectar.
     </p>}
    {!canManage && <p className="mt-4 text-xs text-[var(--mira-apps-muted)]">Você está visualizando as integrações acessíveis ao seu perfil. Consulte um administrador para gerenciar conexões.</p>}
    {loading ? <div role="status" className="mt-9 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
     {Array.from({length:8},(_,i)=><div key={i} className="h-[140px] animate-pulse rounded-xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-card)]" />)}
    </div> : nativeCatalog.isError && !nativeCatalog.data && curatedCatalog.isError && !curatedCatalog.data ?
     <div role="alert" className="mt-9 rounded-xl border border-[var(--mira-apps-border)] p-6 text-sm">Não foi possível carregar o catálogo. <button type="button" onClick={refresh} className="underline">Tentar novamente</button></div> :
     visible.length===0 ? <div className="mt-9 rounded-xl border border-[var(--mira-apps-border)] px-5 py-16 text-center text-sm text-[var(--mira-apps-muted)]">Nenhum app encontrado com os filtros selecionados.</div> :
     <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {shown.map(item=><button key={item.id} type="button" onClick={()=>setSelected(item)}
       aria-label={"Abrir detalhes de "+item.name}
       className="group flex min-h-[142px] flex-col justify-between rounded-xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-card)] p-4 text-left transition-[border-color,background-color,transform] duration-150 hover:-translate-y-0.5 hover:border-[var(--mira-apps-blue)] hover:bg-[var(--mira-apps-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-apps-blue)] motion-reduce:transform-none">
       <span className="flex min-w-0 items-center gap-3">
        <span className={"grid h-12 w-12 shrink-0 place-items-center rounded-[11px] text-base font-semibold shadow-sm "+(tone[item.color]||tone.gray)} aria-hidden="true">{brandLogos[item.id] ? <Image src={brandLogos[item.id]} alt="" width={27} height={27} unoptimized /> : item.initials}</span>
        <span className="min-w-0"><span className="block truncate text-sm font-semibold">{item.name}</span>
         <span className="mt-1 block truncate text-xs text-[var(--mira-apps-muted)]">{item.description}</span>
        </span>
       </span>
       <span className="flex items-end justify-between gap-2">
        <State item={item}/>
        <span className="text-[var(--mira-apps-muted)] group-hover:text-[var(--mira-apps-white)]"><ArrowRight size={16} aria-hidden="true"/></span>
       </span>
      </button>)}
     </div>}
    {visible.length>shown.length && <div className="mt-6 flex justify-center"><button type="button" onClick={()=>setLimit(value=>value+32)} className="rounded-xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-chip)] px-5 py-2.5 text-sm font-medium hover:bg-[var(--mira-apps-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-apps-blue)]">Mostrar mais ({shown.length} de {visible.length})</button></div>}
    <p className="mt-6 text-xs leading-5 text-[var(--mira-apps-muted)]">O catálogo inclui ferramentas conhecidas pela MIRA mesmo sem Composio ativo. Disponibilidade, autorização e conexão ativa são verificações distintas. Nenhuma integração é ativada automaticamente.</p>
   </>}
  </main>
  {selected && <div className="fixed inset-0 z-[80] flex justify-end bg-[var(--mira-apps-backdrop)]" onMouseDown={event=>{if(event.target===event.currentTarget)setSelected(null);}}>
    <section role="dialog" aria-modal="true" aria-label={"Detalhes de "+selected.name} className="flex h-full w-full max-w-[460px] flex-col border-l border-[var(--mira-apps-border)] bg-[var(--mira-apps-dark)] p-6 shadow-2xl">
     <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-[var(--mira-apps-muted)]">Detalhes do aplicativo</span>
      <button type="button" onClick={()=>setSelected(null)} aria-label="Fechar detalhes" className="rounded-lg p-2 hover:bg-[var(--mira-apps-hover)]"><X size={18}/></button>
     </div>
     <div className="mt-8 flex items-center gap-4">
      <span className={"grid h-16 w-16 shrink-0 place-items-center rounded-xl text-xl font-bold "+(tone[selected.color]||tone.gray)} aria-hidden="true">{brandLogos[selected.id] ? <Image src={brandLogos[selected.id]} alt="" width={36} height={36} unoptimized /> : selected.initials}</span>
      <div><h2 className="text-xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-[var(--mira-apps-muted)]">{selected.category}</p></div>
     </div>
     <p className="mt-6 text-sm leading-6 text-[var(--mira-apps-muted)]">{selected.description}</p>
     <div className="mt-6 border-t border-[var(--mira-apps-border)] pt-5">
      <p className="mb-2 text-xs text-[var(--mira-apps-muted)]">Estado no workspace</p><State item={selected}/>
      {selected.connectedAccountName && <p className="mt-3 text-xs text-[var(--mira-apps-muted)]">Conta registrada: {selected.connectedAccountName}</p>}
      {selected.status==="available" && <p className="mt-4 text-xs leading-5 text-[var(--mira-apps-muted)]">Esta ferramenta consta do catálogo, mas nenhuma conexão ativa foi confirmada para este workspace.</p>}
     </div>
     <div className="mt-auto border-t border-[var(--mira-apps-border)] pt-5">
      {canManage ? <div className="flex flex-col gap-2">
        {selected.external && authOptions.data?.items.some(row=>normalizeAppKey(row.toolkit_slug)===normalizeAppKey(selected.slug)) ?
         <button type="button" disabled={connecting} onClick={()=>void connectApp(selected)}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--mira-apps-blue)] px-4 py-3 text-sm font-semibold text-[var(--mira-apps-white)] disabled:opacity-50">
          {connecting?"Abrindo autorização…":"Conectar conta"} <ArrowRight size={15} aria-hidden="true"/>
         </button> : null}
        <Link href={selected.route} onClick={()=>setSelected(null)}
         className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--mira-apps-border)] px-4 py-3 text-sm font-semibold text-[var(--mira-apps-white)] hover:brightness-110">
         Gerenciar no Data Hub <ArrowRight size={15} aria-hidden="true"/>
        </Link>
        {selected.external && !authOptions.data?.items.some(row=>normalizeAppKey(row.toolkit_slug)===normalizeAppKey(selected.slug)) ?
         <p className="text-xs text-[var(--mira-apps-muted)]">Conexão direta indisponível até configurar a autenticação deste aplicativo.</p> : null}
       </div> : <p className="text-sm text-[var(--mira-apps-muted)]">Solicite permissão de administração para configurar esta integração.</p>}
     </div>
    </section>
  </div>}
  {requestOpen && <div className="fixed inset-0 z-[90] grid place-items-center bg-[var(--mira-apps-backdrop)] p-4" onMouseDown={e=>{if(e.target===e.currentTarget)setRequestOpen(false);}}>
    <section role="dialog" aria-modal="true" aria-label="Solicitar integração" className="w-full max-w-[470px] rounded-2xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-card)] p-6 shadow-2xl">
     <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Solicitar integração</h2>
      <button type="button" onClick={()=>setRequestOpen(false)} aria-label="Fechar solicitação"><X size={18}/></button></div>
     <p className="mt-2 text-sm text-[var(--mira-apps-muted)]">Descreva a ferramenta desejada. Você poderá copiar o pedido e encaminhá-lo ao suporte.</p>
     <label className="mt-6 block text-xs font-semibold">Nome do aplicativo
      <input value={requestName} onChange={e=>setRequestName(e.target.value)} maxLength={120} autoFocus placeholder="Ex.: Sistema da instituição"
       className="mt-2 w-full rounded-lg border border-[var(--mira-apps-border)] bg-[var(--mira-apps-dark)] p-3 text-sm outline-none focus:border-[var(--mira-apps-blue)]"/></label>
     <label className="mt-4 block text-xs font-semibold">Como pretende utilizar?
      <textarea value={requestGoal} onChange={e=>setRequestGoal(e.target.value)} maxLength={700} rows={4} placeholder="Descreva o fluxo ou os dados necessários"
       className="mt-2 w-full resize-y rounded-lg border border-[var(--mira-apps-border)] bg-[var(--mira-apps-dark)] p-3 text-sm outline-none focus:border-[var(--mira-apps-blue)]"/></label>
     <button type="button" onClick={()=>void copyRequest()} className="mt-5 w-full rounded-lg bg-[var(--mira-apps-blue)] px-4 py-3 text-sm font-semibold">Copiar solicitação</button>
     <p className="mt-3 text-xs text-[var(--mira-apps-muted)]">O pedido não será enviado automaticamente.</p>
    </section>
  </div>}
 </div>;
}
