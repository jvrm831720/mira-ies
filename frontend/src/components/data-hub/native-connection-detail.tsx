"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { ArrowLeft, Database, Info, RefreshCw, Settings2 } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { connectionState, runState, type DisplayState } from "./data-hub-model";

function Field({ name, children }: { name: string; children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EDF0F2] px-5 py-4 last:border-b-0">
    <dt className="text-xs text-[#7D8590]">{name}</dt><dd className="text-xs font-medium text-[#303844]">{children}</dd>
  </div>;
}

function Time({ value }: { value?: string | null }) {
  if (!value || Number.isNaN(Date.parse(value))) return <>Não registrado</>;
  return <time dateTime={value}>{new Intl.DateTimeFormat("pt-BR", {dateStyle:"medium",timeStyle:"short"}).format(new Date(value))}</time>;
}

const tones: Record<DisplayState["tone"], string> = {
  neutral: "bg-[#F5F6F8] text-[#717A85]",
  blue: "bg-[#EEF4FF] text-[#266DF0]",
  green: "bg-[#EDF8F1] text-[#24714D]",
  amber: "bg-[#FFF8EA] text-[#976200]",
  red: "bg-[#FFF0EF] text-[#B42318]",
};

export function NativeConnectionDetail({ provider }: { provider: "jacad" | "sponte" }) {
  const me = useQuery({queryKey:["org-me"],queryFn:()=>api.me(),retry:false,staleTime:60_000});
  const allowed = hasNavigationPermission(me.data, "data.view");
  const name = provider === "jacad" ? "JACAD" : "Sponte";
  const connection = useQuery({
    queryKey: ["data-hub",me.data?.tenant_id,"detail",provider],
    queryFn: () => provider === "jacad" ? api.jacadConnection() : api.sponteConnection(),
    enabled: allowed, retry: 1, staleTime: 60_000,
  });
  const currentRun = useQuery({
    queryKey: ["data-hub",me.data?.tenant_id,"current-run",provider],
    queryFn: () => provider === "jacad" ? api.jacadSyncCurrent() : api.sponteSyncCurrent(),
    enabled: allowed, retry: 1, staleTime: 45_000,
  });

  return <>
    <Header title={name} subtitle="Detalhe de integração nativa · fonte acadêmica" />
    <main className="mx-auto w-full max-w-[1250px] space-y-5 px-4 pb-12 pt-5 md:px-8 md:pt-7">
      <Link href="/dados" className="inline-flex items-center gap-2 text-xs font-medium text-[#7C8591] hover:text-[#266DF0]"><ArrowLeft size={15} aria-hidden /> Voltar ao Data Hub</Link>
      {me.isLoading ? <p className="text-xs text-[#828B97]">Verificando permissões...</p> :
       me.isError || !allowed ? <section role="alert" className="rounded-lg border border-[#E6E7EA] bg-white p-6 text-xs text-[#B42318]">Acesso negado. A permissão data.view é obrigatória.</section> :
      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EDF0F2] p-5">
            <div className="flex items-center gap-3"><span className="rounded-lg bg-[#F4F6F8] p-2.5"><Database size={20} aria-hidden /></span><div><h2 className="text-sm font-semibold text-[#1E242B]">{name}</h2><p className="mt-1 text-[11px] text-[#818A96]">Conector nativo · Configuração por workspace</p></div></div>
            <button type="button" onClick={() => { void connection.refetch(); void currentRun.refetch(); }} className="inline-flex items-center gap-1.5 rounded-lg border border-[#E6E7EA] px-3 py-2 text-xs font-medium text-[#565E69] hover:bg-[#F9FAFB]"><RefreshCw size={14} aria-hidden /> Atualizar</button>
          </div>
          {connection.isLoading ? <p className="p-5 text-xs text-[#838B96]">Consultando conexão...</p> :
           connection.isError ? <p role="alert" className="p-5 text-xs text-[#B42318]">Falha ao consultar este conector. O estado da conexão é desconhecido.</p> :
           <dl>
             <Field name="Estado"><span className={"rounded-md px-2 py-1 text-[11px] " + tones[connectionState(connection.data).tone]}>{connectionState(connection.data).label}</span></Field>
             <Field name="Configurado">{connection.data?.configured ? "Sim" : "Não"}</Field>
             <Field name="Ativado">{connection.data?.enabled === true ? "Sim" : connection.data?.enabled === false ? "Não" : "Não informado"}</Field>
             <Field name="Credencial cadastrada">{connection.data?.credential_configured === true ? "Sim (não exibida)" : connection.data?.credential_configured === false ? "Não" : "Não informado"}</Field>
             <Field name="Última verificação"><Time value={connection.data?.last_tested_at} /></Field>
             <Field name="Última sincronização"><Time value={connection.data?.last_sync_at} /></Field>
             <Field name="Último estado de sincronização">{connection.data?.last_sync_status || "Não informado"}</Field>
             <Field name="Registros na última sincronização">{typeof connection.data?.last_sync_records === "number" ? connection.data.last_sync_records : "Não informado"}</Field>
             <Field name="Erro registrado">{connection.data?.last_error ? "Sim — consulte os logs sanitizados da integração" : "Nenhum erro declarado no snapshot"}</Field>
           </dl>}
          <div className="flex items-start gap-3 border-t border-[#EDF0F2] bg-[#FBFBFC] p-5">
            <Info size={16} aria-hidden className="shrink-0 text-[#818B96]" />
            <p className="text-[11px] leading-5 text-[#818B96]">Uma conexão configurada não comprova autenticação atual. O Data Hub não executa teste, sincronização nem revogação sem uma ação no fluxo autorizado.</p>
          </div>
        </section>
        <div className="space-y-5">
          <section className="overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
            <div className="border-b border-[#EDF0F2] p-5"><h2 className="text-[13px] font-semibold text-[#242A32]">Execução conhecida</h2><p className="mt-1 text-[11px] text-[#828B97]">Somente o job atual da integração, quando disponível</p></div>
            {currentRun.isLoading ? <p className="p-5 text-xs text-[#858D97]">Consultando execução...</p> :
             currentRun.isError ? <p role="alert" className="p-5 text-xs text-[#A93F2D]">Não foi possível consultar a execução.</p> :
             !currentRun.data ? <p className="p-5 text-xs text-[#8B929C]">Nenhum job atual retornado.</p> :
             <dl>
               <Field name="ID"><span className="max-w-52 break-all font-mono text-[11px]">{currentRun.data.job_id}</span></Field>
               <Field name="Estado"><span className={"rounded-md px-2 py-1 text-[11px] " + tones[runState(currentRun.data.status).tone]}>{runState(currentRun.data.status).label}</span></Field>
               <Field name="Etapa">{currentRun.data.progress?.stage || "Não informada"}</Field>
               <Field name="Progresso">{typeof currentRun.data.progress?.percent === "number" ? String(currentRun.data.progress.percent) + "%" : "Não informado"}</Field>
               <Field name="Tentativa">{typeof currentRun.data.attempt === "number" ? currentRun.data.attempt : "Não informada"}</Field>
             </dl>}
          </section>
          <section className="rounded-xl border border-[#E6E7EA] bg-white p-5">
            <div className="flex items-center gap-2"><Settings2 size={17} className="text-[#78828F]" aria-hidden /><h2 className="text-[13px] font-semibold text-[#29313C]">Gerenciamento</h2></div>
            <p className="mt-2 text-xs leading-5 text-[#828B96]">Autenticação, políticas de mapeamento e sincronização seguem o contrato existente. Nada é executado nesta página.</p>
            <Link href="/conectores" className="mt-4 inline-flex rounded-lg bg-[#15191E] px-3 py-2 text-xs font-medium text-white hover:bg-[#303A45]">Abrir configurações nativas</Link>
          </section>
        </div>
      </div>}
    </main>
  </>;
}
