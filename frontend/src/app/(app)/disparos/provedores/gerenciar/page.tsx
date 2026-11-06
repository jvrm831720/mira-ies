"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { dispatchApi, type DispatchProviderAccount } from "@/lib/dispatch-api";

export default function DispatchProvidersPage() {
  const [accounts, setAccounts] = useState<DispatchProviderAccount[]>([]);
  const [provider, setProvider] = useState<"resend"|"twilio">("resend");
  const [apiKey, setApiKey] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [accountSid, setAccountSid] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const refresh=useCallback(async()=>{
    try {setAccounts((await dispatchApi.providers()).items);setError(null);}
    catch(e){setError(e instanceof Error ? e.message : "Acesso indisponível.");}
  },[]);
  useEffect(()=>{void refresh();},[refresh]);

  async function run(task:()=>Promise<unknown>,success:string){
    setBusy(true);
    try{await task();toast.success(success);await refresh();}
    catch(e){toast.error(e instanceof Error?e.message:"Operação falhou.");}
    finally{setBusy(false);}
  }
  async function configure(){
    const credentials: Record<string, string> = provider==="resend"
      ? {api_key:apiKey,from_email:fromEmail,webhook_secret:webhookSecret}
      : {account_sid:accountSid,auth_token:authToken,from_number:fromNumber};
    await run(async()=>{
      await dispatchApi.configureProvider(provider,credentials);
      setApiKey("");setAuthToken("");setWebhookSecret("");setFromNumber("");setFromEmail("");setAccountSid("");
    },"Credenciais criptografadas e armazenadas. Conta permanece desabilitada até verificação e aprovação.");
  }
  const state=accounts.find(item=>item.provider===provider);
  return <>
    <Header title="Provedores" subtitle="Credenciais de envio isoladas e ativadas por organização" />
    <main className="mx-auto max-w-4xl space-y-5 px-4 py-6 md:px-8">
      <Link href="/disparos" className="text-sm text-[var(--color-legacy-2563eb)]">Voltar a Disparos</Link>
      <p className="text-sm text-[var(--color-legacy-85858b)]">Configure uma conta por workspace. O servidor só aceita envio real após validação dos provedores, autorização do destinatário e habilitação operacional explícita.</p>
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm">{error}</p>}
      <section className="space-y-4 rounded-xl border border-[var(--color-legacy-e7e7e9)] bg-white p-5">
        <h2 className="font-semibold">Configurar remetente</h2>
        <label className="block max-w-sm text-xs">Provedor
          <select value={provider} onChange={e=>setProvider(e.target.value as "resend"|"twilio")}
            className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm">
            <option value="resend">Resend (e-mail)</option>
            <option value="twilio">Twilio (SMS)</option>
          </select>
        </label>
        <p className="text-sm text-[var(--color-legacy-85858b)]">Estado atual: <strong>{state?.status === "active" ? "Ativo" : state ? "Desabilitado" : "Não configurado"}</strong>
          {state?.last_verified_at ? " · Verificado em "+new Date(state.last_verified_at).toLocaleString("pt-BR") : ""}</p>
        {provider==="resend"?<div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs">API key
            <input type="password" autoComplete="off" value={apiKey} onChange={e=>setApiKey(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
          <label className="text-xs">E-mail remetente verificado
            <input value={fromEmail} onChange={e=>setFromEmail(e.target.value)}
              placeholder="equipe@instituicao.edu.br" className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
          <label className="text-xs sm:col-span-2">Webhook signing secret (Svix)
            <input type="password" autoComplete="off" value={webhookSecret} onChange={e=>setWebhookSecret(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
        </div>:<div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs">Account SID
            <input value={accountSid} onChange={e=>setAccountSid(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
          <label className="text-xs">Auth token
            <input type="password" autoComplete="off" value={authToken} onChange={e=>setAuthToken(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
          <label className="text-xs sm:col-span-2">Número autorizado
            <input value={fromNumber} onChange={e=>setFromNumber(e.target.value)}
              placeholder="+5521999999999" className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
        </div>}
        <button type="button" disabled={busy || (provider==="resend"
          ? !apiKey||!fromEmail||!webhookSecret : !accountSid||!authToken||!fromNumber)}
          onClick={()=>void configure()} className="rounded-lg bg-[var(--color-legacy-202124)] px-4 py-2 text-sm text-white disabled:opacity-50">
          Salvar credenciais criptografadas
        </button>
      </section>
      {state && <section className="space-y-4 rounded-xl border border-[var(--color-legacy-e7e7e9)] bg-white p-5">
        <h2 className="font-semibold">Verificar e ativar</h2>
        <p className="text-sm text-[var(--color-legacy-85858b)]">A verificação consulta os provedores oficiais. Outro administrador deve aprovar a ativação. Esta etapa não envia mensagens.</p>
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} onClick={()=>void run(()=>dispatchApi.verifyProvider(provider),"Credenciais verificadas.")}
            className="rounded-lg border border-[var(--color-legacy-dadadd)] px-4 py-2 text-sm disabled:opacity-50">Verificar conta</button>
          <button disabled={busy||state.status!=="active"} onClick={()=>void run(()=>dispatchApi.disableProvider(provider),"Provedor desabilitado.")}
            className="rounded-lg border border-[var(--color-legacy-dadadd)] px-4 py-2 text-sm disabled:opacity-50">Desabilitar</button>
        </div>
        <label className="block text-xs">Referência do termo de ativação
          <input value={evidence} onChange={e=>setEvidence(e.target.value)}
            className="mt-1 w-full max-w-md rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
        </label>
        <button disabled={busy||evidence.length<8||state.status==="active"}
          onClick={()=>void run(()=>dispatchApi.activateProvider(provider,evidence),"Provedor ativado neste workspace.")}
          className="rounded-lg bg-[var(--color-legacy-2563eb)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          Ativar com segundo administrador
        </button>
      </section>}
    </main>
  </>;
}
