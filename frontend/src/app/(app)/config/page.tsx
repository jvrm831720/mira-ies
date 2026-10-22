"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Activity, BrainCircuit, LogOut, Mail, MessageCircle, ShieldCheck, Smartphone, TriangleAlert } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import { copy } from "@/lib/copy";

const providers = [
  { key: "whatsapp", name: "WhatsApp", icon: MessageCircle },
  { key: "email", name: "E-mail", icon: Mail },
  { key: "sms", name: "SMS", icon: Smartphone },
] as const;

export default function ConfigPage() {
  const router = useRouter();
  const status = useQuery({ queryKey: ["agents-status"], queryFn: () => api.agentsStatus() });
  const model = useQuery({ queryKey: ["model-info"], queryFn: () => api.modelInfo(), retry: false });

  function logout() {
    clearAuth();
    toast.message("Sessão encerrada neste dispositivo.");
    router.replace("/login");
  }

  return (
    <>
      <Header title="Configurações" subtitle="Consulte como os canais e o modelo estão operando." />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">Administração</p><h2 className="mt-1 text-xl font-semibold tracking-tight">Visão do ambiente</h2><p className="mt-1 text-sm text-muted-foreground">Informações de estado, sem exibir credenciais ou dados sensíveis.</p></div>

        <Card className="overflow-hidden"><div className="h-1 bg-[var(--brand-indigo)]" /><CardHeader className="flex-row items-start justify-between gap-4"><div><div className="mb-2 inline-flex h-8 w-8 items-center justify-center rounded-xl bg-secondary text-primary"><Activity className="h-4 w-4" /></div><CardTitle>Canais de retenção</CardTitle><CardDescription className="mt-1">Providers habilitados neste ambiente.</CardDescription></div><span className={`rounded-full px-3 py-1.5 text-[10px] font-semibold ${status.data?.dry_run_default ? "bg-[#eef0ff] text-[#3848b5]" : "bg-[#fff0ed] text-[#b84336]"}`}>{status.isLoading ? "Verificando" : status.data?.dry_run_default ? "Simulação padrão" : "Modo real padrão"}</span></CardHeader>
          <CardContent className="space-y-5">
            {status.isLoading ? <div className="grid gap-3 sm:grid-cols-3">{providers.map((provider) => <Skeleton key={provider.key} className="h-[90px] rounded-xl" />)}</div> : status.isError ? <div role="alert" className="flex items-center gap-2 rounded-xl bg-red-50 p-4 text-xs text-red-800"><TriangleAlert className="h-4 w-4" />Não foi possível consultar o estado dos providers.</div> : <div className="grid gap-3 sm:grid-cols-3">{providers.map(({ key, name, icon: Icon }) => { const provider = status.data?.providers[key] || "—"; const simulation = provider === "dry_run"; return <div key={key} className="flex items-center gap-3 rounded-xl border border-border/80 p-4"><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary text-primary"><Icon className="h-[18px] w-[18px]" /></span><div className="min-w-0 flex-1"><p className="text-xs font-semibold">{name}</p><p className="mt-1 truncate text-[10px] text-muted-foreground">{simulation ? "Sem envio real" : `Provider: ${provider}`}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-semibold ${simulation ? "bg-[#eef0ff] text-[#3848b5]" : "bg-[#e9f7f0] text-[#287653]"}`}>{simulation ? "Simulação" : "Conectado"}</span></div>; })}</div>}
            {status.data && <div className="grid gap-3 border-t border-border pt-4 sm:grid-cols-3"><ConfigDatum label="Intervalo mínimo" value={`${status.data.anti_spam.min_hours_between_contact} horas`} /><ConfigDatum label="Máximo semanal" value={`${status.data.anti_spam.max_contacts_per_week} contatos/aluno`} /><ConfigDatum label="Fila de execução" value={status.data.queue?.name || "Configurada"} /></div>}
            <p className="flex items-start gap-2 rounded-xl bg-muted/40 p-3 text-[11px] leading-relaxed text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />A Mira permanece em simulação por padrão, a menos que a configuração do ambiente permita outra operação. Esta tela é somente informativa.</p>
          </CardContent>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card><CardHeader><div className="mb-2 grid h-8 w-8 place-items-center rounded-xl bg-[#fff0ed] text-[#cf5e52]"><BrainCircuit className="h-4 w-4" /></div><CardTitle>Modelo preditivo</CardTitle><CardDescription>Transparência e escopo da análise.</CardDescription></CardHeader><CardContent className="space-y-3">
            {model.isLoading ? <div className="space-y-2"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div> : model.isError ? <p role="alert" className="rounded-xl bg-muted/50 p-3 text-xs text-muted-foreground">Informações do modelo indisponíveis no momento.</p> : <div className="grid grid-cols-2 gap-2"><ConfigDatum label="Status" value={model.data?.status || "Indisponível"} /><ConfigDatum label="Versão" value={model.data?.version || "—"} /><ConfigDatum label="Escopo" value={model.data?.model_scope || "—"} /><ConfigDatum label="Dados" value={model.data?.training_data || "—"} />{typeof model.data?.auc === "number" && <ConfigDatum label="AUC informado" value={model.data.auc.toFixed(3)} />}</div>}
            <p className="rounded-xl border border-[#dce0ff] bg-[#f3f4ff] p-3 text-xs leading-relaxed text-[#313e9e]">{model.data?.disclaimer || copy.modelDisclaimerFallback}</p>
          </CardContent></Card>

          <Card><CardHeader><div className="mb-2 grid h-8 w-8 place-items-center rounded-xl bg-secondary text-primary"><ShieldCheck className="h-4 w-4" /></div><CardTitle>Sessão e segurança</CardTitle><CardDescription>Gerencie o acesso neste navegador.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="rounded-xl border border-border/80 p-4"><p className="text-xs font-semibold">Sessão atual</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">Seu token de acesso está armazenado apenas neste navegador e vinculado à instituição autenticada.</p></div><Button variant="outline" onClick={logout}><LogOut className="h-4 w-4" /> Sair e limpar sessão</Button></CardContent></Card>
        </div>
      </main>
    </>
  );
}

function ConfigDatum({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-xl bg-muted/35 p-3"><p className="text-[10px] font-medium text-muted-foreground">{label}</p><p className="mt-1 truncate text-xs font-semibold" title={value}>{value}</p></div>;
}
