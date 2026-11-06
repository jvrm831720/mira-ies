"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowRight, ChevronDown, Plus, RefreshCw, ShieldCheck } from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { api } from "@/lib/api";
import { getVisibleNavigation, hasNavigationPermission } from "@/components/layout/navigation";
import { dispatchApi, type CampaignDraft, type DispatchCampaign } from "@/lib/dispatch-api";
import { DispatchNavigation } from "./dispatch-navigation";
import { DispatchOverview } from "./dispatch-overview";
import { CampaignBuilder } from "./campaign-builder";
import { CampaignIndex } from "./campaign-index";
import { CampaignDetailDrawer } from "./campaign-detail";
import { DispatchControlCenter } from "./dispatch-control-center";
import { DispatchResults } from "./dispatch-results";
import type { DispatchSection } from "./dispatch-types";

export function DispatchExperience() {
  const queryClient = useQueryClient();
  const [section, setSection] = useState<DispatchSection>("overview");
  const [building, setBuilding] = useState(false);
  const [selected, setSelected] = useState<DispatchCampaign|null>(null);
  const [advanced, setAdvanced] = useState(false);
  const me=useQuery({ queryKey:["org-me"],queryFn:api.me,staleTime:60_000,retry:false });
  const tenantId=me.data?.tenant_id||"";
  const userId=me.data?.user_id||"";
  const allowedByNavigation = getVisibleNavigation(me.data).some(group=>
    group.items.some(item=>item.href==="/disparos"));
  const canView=allowedByNavigation && hasNavigationPermission(me.data,"campaigns.view");
  const canCreate=canView && hasNavigationPermission(me.data,"campaigns.create");
  const canAudit=canView && hasNavigationPermission(me.data,"audit.view");
  const canManageProviders=canView && hasNavigationPermission(me.data,"settings.manage");
  const qkey=["dispatch","campaigns",tenantId,userId] as const;
  const campaigns=useQuery({
    queryKey:qkey,queryFn:()=>dispatchApi.campaigns(),
    enabled:canView && !!tenantId && !!userId,
    staleTime:25_000,retry:false,refetchOnWindowFocus:false,
  });
  const metrics=useQuery({
    queryKey:["dispatch","metrics",tenantId,userId],queryFn:dispatchApi.metrics,
    enabled:canView && !!tenantId && !!userId,
    staleTime:25_000,retry:false,refetchOnWindowFocus:false,
  });
  const sources=useQuery({
    queryKey:["dispatch","sources",tenantId,userId],queryFn:dispatchApi.sources,
    enabled:canCreate && building,staleTime:60_000,retry:false,
  });
  const templates=useQuery({
    queryKey:["dispatch","templates",tenantId,userId],queryFn:dispatchApi.templates,
    enabled:canCreate && building,staleTime:60_000,retry:false,
  });
  const financial=useQuery({
    queryKey:["dispatch","financial",tenantId,userId],queryFn:dispatchApi.financial,
    enabled:canAudit && section==="results",staleTime:30_000,retry:false,
    refetchOnWindowFocus:false,
  });
  const create=useMutation({
    mutationFn:(draft:CampaignDraft)=>dispatchApi.create(draft),
    onSuccess:()=>{ void queryClient.invalidateQueries({queryKey:["dispatch","campaigns",tenantId,userId]});
      void queryClient.invalidateQueries({queryKey:["dispatch","metrics",tenantId,userId]});
      setBuilding(false);setSection("campaigns");toast.success("Rascunho criado. Nenhuma mensagem foi enviada."); },
  });
  const onClose=useCallback(()=>setSelected(null),[]);
  useEffect(()=>{
    // Existing deep links to individual contacts and approved proposals must remain functional.
    const url=new URLSearchParams(window.location.search);
    if(url.get("mode")==="individual" || url.has("proposal")) {
      window.location.replace("/disparos/console"+window.location.search);
    }
  },[]);
  useEffect(()=>{setSelected(null);setBuilding(false);setSection("overview");},[tenantId,userId]);

  if(me.isLoading)return <main role="status" className="mira-page p-8 text-[12px] text-[var(--color-muted)]">Verificando permissões da operação…</main>;
  if(me.isError||!canView)return <main role="alert" className="mira-page p-8 text-[13px] text-[var(--color-slate-600)]">
    Acesso à operação indisponível. Verifique permissões do workspace e módulo de Dispatch.
  </main>;

  function refresh(){
    void campaigns.refetch();void metrics.refetch();
    if(section==="results"&&canAudit)void financial.refetch();
  }
  return <>
    <Header title="Operação" subtitle="Campanhas, mensagens e evidências no mesmo contexto" />
    <main className="mira-page min-h-dvh bg-[var(--color-canvas)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-4 md:px-7">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">MIRA / Operação</p>
          <h1 className="mt-1 text-[19px] font-semibold tracking-tight">Comunicação institucional</h1>
          <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Planeje, autorize, monitore e verifique — sem confundir proposta, disparo e resultado.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={refresh} disabled={campaigns.isFetching||metrics.isFetching}
            className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 text-[12px] font-medium hover:bg-[var(--color-panel)] disabled:opacity-50">
            <RefreshCw className="h-3.5 w-3.5" /> Atualizar
          </button>
          {canCreate && <button type="button" onClick={()=>{setBuilding(true);setSection("campaigns");}}
            className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-ink)] px-3 text-[12px] font-medium text-white">
            <Plus className="h-3.5 w-3.5" /> Nova campanha
          </button>}
        </div>
      </div>
      <DispatchNavigation section={section} onSectionChange={tab=>{setSection(tab);setBuilding(false);}}
        canManageProviders={canManageProviders}/>
      <div className="mx-auto max-w-[1500px] space-y-5 px-4 py-5 md:px-7">
        {campaigns.isError && <p role="alert" className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3 text-[12px] text-[var(--color-red)]">
          Não foi possível consultar todas as campanhas. <button type="button" className="underline" onClick={()=>void campaigns.refetch()}>Tentar novamente</button>
        </p>}
        {section==="overview" && <DispatchOverview
          metrics={metrics.data||null} campaigns={campaigns.data?.items||[]}
          loading={metrics.isLoading||campaigns.isLoading} failed={metrics.isError}
          onRetry={refresh} onChange={setSection} />}
        {section==="campaigns" && <>
          {building && (sources.isLoading||templates.isLoading) && <div role="status" className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-6 text-[12px] text-[var(--color-muted)]">
            Carregando fontes e modelos autorizados…
          </div>}
          {building && (sources.isError||templates.isError) && <div role="alert" className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-6 text-[12px] text-[var(--color-red)]">
            Não foi possível validar origens ou modelos. <button className="underline" type="button" onClick={()=>{void sources.refetch();void templates.refetch();}}>Tentar novamente</button>
          </div>}
          {building && sources.data && templates.data && <CampaignBuilder
            key={tenantId+":"+userId} sources={sources.data.items} templates={templates.data.items}
            profile={me.data?.operation_profile} busy={create.isPending}
            onCreate={payload=>create.mutateAsync(payload)} onCancel={()=>setBuilding(false)}/>}
          <CampaignIndex campaigns={campaigns.data?.items||[]} loading={campaigns.isLoading}
            error={campaigns.isError} onRetry={()=>void campaigns.refetch()} onOpen={setSelected}/>
        </>}
        {section==="monitor" && <DispatchControlCenter
          campaigns={campaigns.data?.items||[]} metrics={metrics.data||null}
          loading={campaigns.isLoading} error={campaigns.isError} onSelect={setSelected}/>}
        {section==="results" && <DispatchResults metrics={metrics.data||null}
          financial={financial.data||null} canAudit={canAudit}
          financialLoading={financial.isLoading} financialError={financial.isError}/>}
        <section className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white">
          <button type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-[12px] font-medium text-[var(--color-slate-600)]"
            aria-expanded={advanced} onClick={()=>setAdvanced(v=>!v)}>
            Recursos existentes da MIRA <ChevronDown className={"h-4 w-4 transition-transform "+(advanced?"rotate-180":"")}/>
          </button>
          {advanced && <div className="flex flex-wrap gap-2 border-t border-[var(--color-border)] p-4">
            {([
              {href:"/disparos/console",label:"Console avançado / contato individual"},
              {href:"/campanhas",label:"Propostas de permanência"},
              {href:"/disparos/modelos",label:"Modelos aprovados"},
              {href:"/workflows",label:"Workflows"},
            ] as const).map(item=><Link key={item.href} href={item.href}
              className="inline-flex h-9 items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[11px] hover:bg-[var(--color-panel)]">
              {item.label}<ArrowRight className="h-3 w-3"/>
            </Link>)}
            {canManageProviders && <Link href="/disparos/provedores" className="inline-flex h-9 items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[11px]">Provedores <ArrowRight className="h-3 w-3"/></Link>}
          </div>}
        </section>
        <p className="flex items-start gap-2 text-[11px] leading-relaxed text-[var(--color-muted)]"><ShieldCheck className="h-4 w-4 shrink-0"/> A interface não ativa provedores, não aprova campanhas e não envia mensagens ao consultar registros. O backend continua responsável por MFA, RBAC, autorização, consentimento e idempotência.</p>
      </div>
    </main>
    {selected && <CampaignDetailDrawer key={selected.id} campaign={selected} tenantId={tenantId}
      userId={userId} onClose={onClose} onOpenMonitor={()=>setSection("monitor")} />}
  </>;
}
