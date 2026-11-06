"use client";
/* eslint-disable @next/next/no-img-element -- official provider favicons with accessible local initial fallback */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft, ArrowRight, Check, ChevronRight, Clock3, ExternalLink,
  Info, Plug, Plus, RefreshCw, Search, ShieldCheck, X,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { hasNavigationPermission } from "@/components/layout/navigation";
import {
  categories, filterApps, mergeAppCatalog,
  type AppCategory, type AppEntry, type AppStatus,
} from "./apps-catalog-model";
import styles from "./apps-catalog.module.css";

type Tab = "popular" | "connected" | "discover";
const labels: Record<AppStatus,string> = {
  connected:"Conectado", configured:"Habilitado", listed:"No catálogo",
  request:"Sob consulta",unknown:"Não verificado",
};
const examples: Record<string,string> = {
  gmail:"G",outlook:"O",slack:"S",googledrive:"▲",googlesheets:"▦",
  googlecalendar:"31",whatsapp:"◉",jacad:"J",sponte:"S",sophia:"S",
  moodle:"m",canvas:"C",omie:"O",asaas:"A",openai:"✳",stripe:"S",
  notion:"N",hubspot:"H",salesforce:"S",microsoft_teams:"T",
};
const brandedDomains:Record<string,string>={
  whatsapp:"whatsapp.com",gmail:"gmail.com",outlook:"outlook.com",googlecalendar:"calendar.google.com",
  googledrive:"drive.google.com",googlesheets:"sheets.google.com",slack:"slack.com",
  jacad:"jacad.com.br",sponte:"sponte.com.br",sophia:"sophia.com.br",
  moodle:"moodle.org",canvas:"instructure.com",omie:"omie.com.br",
  asaas:"asaas.com",openai:"openai.com",notion:"notion.so",salesforce:"salesforce.com",
  hubspot:"hubspot.com",stripe:"stripe.com",airtable:"airtable.com",
  trello:"trello.com",clickup:"clickup.com",calendly:"calendly.com",
  share_point:"microsoft.com",one_drive:"onedrive.live.com",microsoft_teams:"teams.microsoft.com",
  zoom:"zoom.us",zendesk:"zendesk.com",freshdesk:"freshdesk.com",intercom:"intercom.com",
};
const iconTone:Record<string,string>={
  whatsapp:"green",gmail:"rainbow",outlook:"blue",googlecalendar:"blue",
  googledrive:"rainbow",slack:"rainbow",jacad:"blue",sponte:"blue",sophia:"blue",
  moodle:"orange",canvas:"red",omie:"cyan",asaas:"blue",openai:"neutral",
  googlesheets:"green",stripe:"purple",notion:"neutral",hubspot:"orange",
};
function Status({ status }: {status:AppStatus}) {
  return <span className={styles.status} data-status={status}>
    {status==="connected"?<Check size={13} aria-hidden="true"/>:
     status==="request"?<Clock3 size={13} aria-hidden="true"/>:null}
    {labels[status]}
  </span>;
}
function AppLogo({app}:{app:AppEntry}) {
  const domain=brandedDomains[app.id];
  return <span className={styles.logo} data-tone={iconTone[app.id]||"neutral"} aria-hidden="true">
    {domain ? <img className={styles.brandIcon}
      src={"https://www.google.com/s2/favicons?domain="+domain+"&sz=128"} alt=""
      loading="lazy" referrerPolicy="no-referrer" onError={e=>{e.currentTarget.style.display="none";}}/> : null}
    <span className={styles.fallbackInitial}>{examples[app.id]||app.name.slice(0,1).toLocaleUpperCase("pt-BR")}</span>
  </span>;
}
function AppCard({app,onOpen}:{app:AppEntry,onOpen:(app:AppEntry)=>void}) {
  return <button type="button" className={styles.card} onClick={()=>onOpen(app)} aria-label={app.name+": "+labels[app.status]}>
    <div className={styles.cardTop}><AppLogo app={app}/>
      <div className={styles.cardIdentity}><strong>{app.name}</strong><span>{app.description}</span></div>
    </div>
    <div className={styles.cardFoot}><Status status={app.status}/>
      <span className={styles.cardMore} aria-hidden="true"><ChevronRight size={17}/></span>
    </div>
  </button>;
}
function AppDetail({app,onClose,canManage}:{app:AppEntry,onClose:()=>void,canManage:boolean}) {
  useEffect(()=>{
    const onKey=(event:KeyboardEvent)=>{if(event.key==="Escape")onClose();};
    window.addEventListener("keydown",onKey);
    return ()=>window.removeEventListener("keydown",onKey);
  },[onClose]);
  return <div className={styles.overlay} role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}>
    <section className={styles.detail} role="dialog" aria-modal="true" aria-labelledby="mira-app-detail-title">
      <div className={styles.detailToolbar}>
        <button className={styles.iconButton} type="button" onClick={onClose} aria-label="Voltar ao catálogo"><ArrowLeft size={18}/></button>
        <span>Detalhes da integração</span>
        <button className={styles.iconButton} type="button" onClick={onClose} aria-label="Fechar detalhes"><X size={18}/></button>
      </div>
      <div className={styles.detailContent}>
        <AppLogo app={app}/>
        <h2 id="mira-app-detail-title">{app.name}</h2>
        <p>{app.description}</p>
        <Status status={app.status}/>
        <div className={styles.detailSection}>
          <h3>Sobre esta integração</h3>
          <p>Conecte ferramentas da sua instituição à MIRA para organizar informações e apoiar processos autorizados do workspace.</p>
          <p>O acesso depende das permissões do seu cargo, da configuração institucional e da habilitação de cada recurso.</p>
        </div>
        <div className={styles.detailSection}>
          <h3>Estado no seu workspace</h3>
          <p>{app.status==="connected"?"Há uma conta ativa registrada para este aplicativo.":
             app.status==="configured"?"Há configuração registrada, mas isso não confirma uma conta ativa ou sincronização recente.":
             app.status==="listed"?"O aplicativo está no catálogo, mas não há conexão ativa confirmada para este workspace.":
             "Ainda não há uma conexão ativa confirmada. Consulte as opções de habilitação da instituição."}</p>
        </div>
        {canManage&&app.href?<Link href={app.href} className={styles.primaryAction} onClick={onClose}>
          Abrir configuração existente <ExternalLink size={16}/>
        </Link>:canManage?<Link href="/dados" className={styles.primaryAction} onClick={onClose}>
          Ver conexões da instituição <ArrowRight size={16}/>
        </Link>:<p className={styles.subtle}>Solicite ao administrador do workspace para consultar a configuração.</p>}
        <p className={styles.footnote}><ShieldCheck size={15}/> A consulta do catálogo não autoriza envios, pagamentos ou acesso a dados externos.</p>
      </div>
    </section>
  </div>;
}
function RequestModal({onClose}:{onClose:()=>void}) {
  const [name,setName]=useState("");
  const [purpose,setPurpose]=useState("");
  const [copied,setCopied]=useState(false);
  async function copyRequest(){
    const message="Solicitação de integração MIRA\nFerramenta: "+name.trim()+"\nNecessidade: "+purpose.trim();
    try {await navigator.clipboard.writeText(message);setCopied(true);toast.success("Solicitação copiada.");}
    catch {toast.error("Não foi possível copiar. Copie o texto manualmente.");}
  }
  useEffect(()=>{const fn=(event:KeyboardEvent)=>{if(event.key==="Escape")onClose();};window.addEventListener("keydown",fn);return ()=>window.removeEventListener("keydown",fn);},[onClose]);
  return <div className={styles.overlay} role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <section className={styles.requestDialog} role="dialog" aria-modal="true" aria-labelledby="mira-request-title">
      <div className={styles.detailToolbar}><h2 id="mira-request-title">Solicitar integração</h2>
        <button className={styles.iconButton} onClick={onClose} type="button" aria-label="Fechar"><X size={18}/></button>
      </div>
      <div className={styles.requestForm}>
        <p>Prepare a solicitação para encaminhar à equipe responsável. Este formulário não envia uma solicitação automaticamente.</p>
        <label>Nome da ferramenta<input value={name} onChange={e=>{setName(e.target.value);setCopied(false);}} maxLength={100} placeholder="Ex.: sistema acadêmico da instituição" required/></label>
        <label>Como pretende usar?<textarea value={purpose} onChange={e=>{setPurpose(e.target.value);setCopied(false);}} rows={4} maxLength={500} placeholder="Descreva os dados ou processos que gostaria de conectar."/></label>
        <button type="button" className={styles.primaryAction} disabled={!name.trim()} onClick={()=>void copyRequest()}>
          {copied?<Check size={16}/>:<Plus size={16}/>} {copied?"Copiado":"Copiar solicitação"}
        </button>
      </div>
    </section>
  </div>;
}
export function AppsCatalog() {
  const [tab,setTab]=useState<Tab>("popular");
  const [category,setCategory]=useState<"Todos"|AppCategory>("Todos");
  const [search,setSearch]=useState("");
  const [selected,setSelected]=useState<AppEntry|null>(null);
  const [requestOpen,setRequestOpen]=useState(false);
  const [visibleCount,setVisibleCount]=useState(36);
  const me=useQuery({queryKey:["org-me"],queryFn:()=>api.me(),retry:false,staleTime:60_000});
  const tenant=me.data?.tenant_id;
  const canSee=hasNavigationPermission(me.data,"data.view");
  const canManage=hasNavigationPermission(me.data,"settings.manage");
  const native=useQuery({
    queryKey:["apps",tenant,"native-catalog"],queryFn:()=>api.listConnectors(),
    enabled:canSee,staleTime:120_000,retry:1,
  });
  const live=useQuery({
    queryKey:["apps",tenant,"live-catalog"],queryFn:()=>api.composioCatalog(),
    enabled:canSee&&canManage,staleTime:300_000,retry:false,
  });
  const connections=useQuery({
    queryKey:["apps",tenant,"connections"],queryFn:()=>api.composioConnections(),
    enabled:canSee&&canManage,staleTime:45_000,retry:1,
  });
  const jacad=useQuery({
    queryKey:["apps",tenant,"jacad"],queryFn:()=>api.jacadConnection(),
    enabled:canSee,staleTime:60_000,retry:1,
  });
  const sponte=useQuery({
    queryKey:["apps",tenant,"sponte"],queryFn:()=>api.sponteConnection(),
    enabled:canSee,staleTime:60_000,retry:1,
  });
  const items=useMemo(()=>mergeAppCatalog(
    live.data?.items,native.data?.connectors,connections.data?.items,
    {jacad:jacad.data?.status==="connected"?"connected":!!jacad.data?.configured,
      sponte:sponte.data?.status==="connected"?"connected":!!sponte.data?.configured}
  ),[live.data?.items,native.data?.connectors,connections.data?.items,jacad.data?.configured,sponte.data?.configured]);
  const displayed=useMemo(()=>filterApps(items,search,category,tab),[items,search,category,tab]);
  const connected=items.filter(item=>item.status==="connected"||item.status==="configured").length;
  useEffect(()=>{setVisibleCount(36);},[search,category,tab]);
  const visibleItems=displayed.slice(0,visibleCount);
  if(me.isLoading)return <main className={styles.page}><p className={styles.loading} role="status">Carregando seu workspace...</p></main>;
  if(!canSee)return <main className={styles.page}><section className={styles.access}><ShieldCheck size={22}/><h1>Acesso restrito</h1><p>É necessário ter permissão de visualização de dados para explorar as integrações.</p></section></main>;
  return <main className={styles.page}>
    <div className={styles.topbar}><span>Apps e integrações</span><span className={styles.topbarIcon}><Plug size={17}/></span></div>
    <div className={styles.content}>
      <div className={styles.hero}>
        <div><h1>Apps e integrações</h1><p>Conecte a MIRA às ferramentas que sua operação já usa.</p></div>
        <button className={styles.requestButton} type="button" onClick={()=>setRequestOpen(true)}><Plus size={17}/> Solicitar integração</button>
      </div>
      <div className={styles.tabs} role="tablist" aria-label="Explorar apps">
        {[["popular","Mais usados"],["connected","Conectados"],["discover","Descobrir"]].map(([key,label])=>
          <button key={key} type="button" role="tab" aria-selected={tab===key} className={styles.tab} data-active={tab===key}
          onClick={()=>setTab(key as Tab)}>{label}</button>)}
      </div>
      <div className={styles.tools}>
        <label className={styles.search}><Search size={18}/><span className="sr-only">Buscar aplicativos</span>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar apps" type="search"/>
        </label>
        <div className={styles.chips} role="group" aria-label="Categoria">
          {categories.map(value=><button key={value} type="button" className={styles.chip} data-active={category===value}
            aria-pressed={category===value} onClick={()=>setCategory(value)}>{value}</button>)}
        </div>
        <span className={styles.count}>{displayed.length} encontrados</span>
      </div>
      {(live.isError&&canManage)&&<p className={styles.notice} role="status"><Info size={15}/>
        Parte do catálogo dinâmico está temporariamente indisponível. As integrações conhecidas continuam visíveis, sem presumir disponibilidade ou conexão.</p>}
      {(native.isError)&&<p className={styles.notice} role="status"><Info size={15}/>
        O catálogo de conectores nativos não pôde ser atualizado agora.</p>}
      {(connections.isError&&canManage)&&<p className={styles.notice} role="status"><Info size={15}/>
        Não foi possível confirmar todas as conexões; consulte os detalhes antes de executar operações.</p>}
      <div className={styles.grid} aria-live="polite">
        {visibleItems.map(app=><AppCard key={app.id} app={app} onOpen={setSelected}/>)}
      </div>
      {visibleCount<displayed.length&&<button type="button" className={styles.moreButton}
        onClick={()=>setVisibleCount(current=>current+36)}>Mostrar mais aplicativos ({displayed.length-visibleCount} restantes)</button>}
      {displayed.length===0&&<div className={styles.empty}>
        <Plug size={28}/><h2>{tab==="connected"?"Nenhum app confirmado nesta seleção":"Nenhum aplicativo encontrado"}</h2>
        <p>Altere a busca ou os filtros para explorar outras opções.</p>
        <button type="button" onClick={()=>{setSearch("");setCategory("Todos");setTab("discover");}}>Ver todos os apps</button>
      </div>}
      <div className={styles.footer}>
        <span>{items.length} aplicativos e conectores catalogados · {connected} com configuração ou conexão registrada</span>
        <button type="button" onClick={()=>{void native.refetch();if(canManage){void live.refetch();void connections.refetch();}void jacad.refetch();void sponte.refetch();}}>
          <RefreshCw size={15}/> Atualizar estados
        </button>
      </div>
      <p className={styles.disclaimer}>Os recursos são disponibilizados conforme o plano, as permissões e a configuração da instituição. Estar no catálogo não significa estar conectado.</p>
    </div>
    {selected&&<AppDetail app={selected} canManage={canManage} onClose={()=>setSelected(null)}/>}
    {requestOpen&&<RequestModal onClose={()=>setRequestOpen(false)}/>}
  </main>;
}
