"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { AlertTriangle, ArrowRight, LockKeyhole, ShieldCheck } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { dispatchApi } from "@/lib/dispatch-api";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { readableDate } from "./dispatch-utils";

const providers=[
  {key:"resend",title:"Resend",channel:"E-mail"},
  {key:"twilio",title:"Twilio",channel:"SMS"},
] as const;
export function DispatchProviders() {
  const me=useQuery({queryKey:["org-me"],queryFn:api.me,staleTime:60_000,retry:false});
  const authorized=hasNavigationPermission(me.data,"settings.manage");
  const data=useQuery({queryKey:["dispatch","providers",me.data?.tenant_id,me.data?.user_id],
    queryFn:dispatchApi.providers,enabled:authorized,staleTime:30_000,retry:false});
  if(me.isLoading)return <main className="mira-page p-8 text-[12px]" role="status">Verificando autorização…</main>;
  if(!authorized)return <main className="mira-page p-8 text-[13px]" role="alert">É necessária a permissão settings.manage para ver provedores.</main>;
  return <>
    <Header title="Canais e provedores" subtitle="Configuração, verificação e ativação por workspace" />
    <main className="mira-page mx-auto max-w-[1200px] space-y-5 px-4 py-5 md:px-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">MIRA Operação / Canais</p>
          <h1 className="mt-1 text-[18px] font-semibold">Provedores de comunicação</h1>
          <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Credenciais nunca são expostas pela interface.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/disparos" className="rounded-md border border-[var(--color-border)] px-3 py-2 text-[12px]">Voltar à operação</Link>
          <Link href="/disparos/provedores/gerenciar" className="inline-flex items-center gap-1 rounded-md bg-[var(--color-ink)] px-3 py-2 text-[12px] font-medium text-white">
            Gerenciar contas <ArrowRight className="h-3 w-3"/>
          </Link>
        </div>
      </div>
      <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] p-4 text-[11px] leading-relaxed text-[var(--color-slate-600)]">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0"/>
        Configurado, verificado, ativo e operacional são quatro condições diferentes. A capacidade de enviar depende de flags, política do tenant, destinatário, canal e comprovações de autorização.
      </div>
      {data.isLoading&&<p role="status" className="text-[12px] text-[var(--color-muted)]">Consultando estados dos provedores…</p>}
      {data.isError&&<p role="alert" className="text-[12px] text-[var(--color-red)]">Não foi possível consultar os provedores. <button className="underline" onClick={()=>void data.refetch()}>Tentar novamente</button></p>}
      {data.data&&<div className="grid gap-3 sm:grid-cols-2">
        {providers.map(provider=>{
          const account=data.data.items.find(item=>item.provider===provider.key);
          return <section key={provider.key} className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-5">
            <div className="flex justify-between gap-2"><div><h2 className="text-[14px] font-semibold">{provider.title}</h2>
              <p className="mt-1 text-[11px] text-[var(--color-muted)]">{provider.channel}</p></div>
              <span className="mira-tag mira-tag--blue">{account?.status==="active"?"Ativo":account?"Desabilitado":"Não configurado"}</span>
            </div>
            <dl className="mt-4 space-y-2">
              {([
                ["Configurado",account ? "Sim" : "Não confirmado"],
                ["Última verificação",readableDate(account?.last_verified_at)],
                ["Ativo na organização",account?.status==="active"?"Sim":"Não"],
                ["Capacidade de envio", "Não verificada por esta tela"],
              ] as Array<[string,string]>).map(([title,value])=><div className="flex justify-between gap-2 border-b border-[var(--color-border-subtle)] pb-2 text-[11px]" key={title}>
                <dt className="text-[var(--color-slate-600)]">{title}</dt><dd className="text-right font-medium">{value}</dd>
              </div>)}
            </dl>
            {!account && <p className="mt-4 text-[11px] text-[var(--color-muted)]">Nenhuma credencial cadastrada para esta integração no workspace.</p>}
            {account?.status==="active"&&!account.last_verified_at&&<p className="mt-4 flex items-start gap-2 text-[11px] text-[var(--color-red)]"><AlertTriangle className="h-3.5 w-3.5 shrink-0"/>Verificação remota ainda não comprovada.</p>}
          </section>;
        })}
      </div>}
      <p className="flex items-start gap-2 text-[11px] leading-relaxed text-[var(--color-muted)]">
        <LockKeyhole className="h-4 w-4 shrink-0"/>WhatsApp não é oferecido como provedor operacional nesta tela porque não há contrato de conta equivalente verificado. Habilitação nunca é inferida de um canal enumerado.
      </p>
    </main>
  </>;
}
