"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  BrainCircuit,
  Building2,
  ExternalLink,
  LogOut,
  Mail,
  MessageCircle,
  Plug,
  Settings2,
  ShieldCheck,
  Smartphone,
  TriangleAlert,
  Users,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { clearAuth, setAccessToken } from "@/lib/auth";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { id: "instituicao", label: "Instituição" },
  { id: "comunicacao", label: "Comunicação" },
  { id: "regras", label: "Regras operacionais" },
  { id: "inteligencia", label: "Inteligência" },
  { id: "seguranca", label: "Segurança" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

const CHANNELS = [
  { key: "whatsapp" as const, name: "WhatsApp", icon: MessageCircle },
  { key: "email" as const, name: "E-mail", icon: Mail },
  { key: "sms" as const, name: "SMS", icon: Smartphone },
];

/** Providers conhecidos que indicam envio real configurado no ambiente. */
const REAL_PROVIDERS = new Set(["waha", "evolution", "resend", "twilio"]);

type ChannelState =
  | { kind: "connected"; label: string; detail: string }
  | { kind: "simulation"; label: string; detail: string }
  | { kind: "unknown"; label: string; detail: string };

function channelState(providerRaw: string | undefined | null): ChannelState {
  const provider = (providerRaw || "").trim();
  if (!provider) {
    return {
      kind: "unknown",
      label: "Desconhecido",
      detail: "A API não informou o provider deste canal.",
    };
  }
  if (provider === "dry_run") {
    return {
      kind: "simulation",
      label: "Simulação",
      detail: "Sem credenciais de envio real neste ambiente (dry-run).",
    };
  }
  if (REAL_PROVIDERS.has(provider)) {
    return {
      kind: "connected",
      label: "Configurado",
      detail: `Provider: ${provider}`,
    };
  }
  return {
    kind: "unknown",
    label: "Não classificado",
    detail: `Valor retornado: ${provider}`,
  };
}

function stateBadgeClass(kind: ChannelState["kind"]) {
  if (kind === "connected") return "bg-[#e9f7f0] text-[#287653]";
  if (kind === "simulation") return "bg-[#eef0ff] text-[#3848b5]";
  return "bg-muted text-muted-foreground";
}

export default function ConfigPage() {
  const router = useRouter();
  const [section, setSection] = useState<SectionId>("instituicao");
  const [mfaEnrollment, setMfaEnrollment] = useState<{secret:string; qr_code:string} | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [mfaMessage, setMfaMessage] = useState<string | null>(null);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const mfaStatus = useQuery({ queryKey: ["mfa-status"], queryFn: () => api.mfaStatus(), retry: false });

  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });

  const status = useQuery({
    queryKey: ["agents-status"],
    queryFn: () => api.agentsStatus(),
    retry: false,
  });

  const model = useQuery({
    queryKey: ["model-info"],
    queryFn: () => api.modelInfo(),
    retry: false,
  });

  async function startMfaEnrollment() {
    setMfaError(null); setMfaMessage(null);
    try { const result = await api.enrollMfa(); setMfaEnrollment(result); }
    catch (error) { setMfaError(error instanceof Error ? error.message : "Não foi possível iniciar a configuração."); }
  }
  async function confirmMfaEnrollment() {
    setMfaError(null); setMfaMessage(null);
    try {
      const result = await api.confirmMfa(mfaCode);
      setAccessToken(result.access_token);
      setRecoveryCodes(result.recovery_codes);
      setMfaEnrollment(null); setMfaCode("");
      await mfaStatus.refetch();
      setMfaMessage("Autenticação multifator ativada. Guarde os códigos de recuperação.");
    } catch (error) { setMfaError(error instanceof Error ? error.message : "Código inválido."); }
  }
  async function disableMfa() {
    setMfaError(null); setMfaMessage(null);
    try {
      const result = await api.disableMfa(mfaCode);
      setAccessToken(result.access_token);
      setMfaCode(""); setRecoveryCodes(null);
      await mfaStatus.refetch();
      setMfaMessage("Autenticação multifator desativada.");
    } catch (error) { setMfaError(error instanceof Error ? error.message : "Não foi possível desativar o MFA."); }
  }
  async function regenerateRecoveryCodes() {
    setMfaError(null); setMfaMessage(null);
    try { const result = await api.regenerateMfaRecoveryCodes(mfaCode); setRecoveryCodes(result.recovery_codes); setMfaCode(""); await mfaStatus.refetch(); }
    catch (error) { setMfaError(error instanceof Error ? error.message : "Não foi possível gerar novos códigos."); }
  }

  function logout() {
    clearAuth();
    toast.message("Sessão encerrada neste dispositivo.");
    router.replace("/login");
  }

  const orgName = me.data?.tenant_name;
  const roleLabel = me.data?.role || "—";

  const channelsSummary = useMemo(() => {
    if (!status.data?.providers) return null;
    const providers = status.data.providers;
    const states = CHANNELS.map(({ key }) => channelState(providers[key]));
    const configured = states.filter((s) => s.kind === "connected").length;
    const simulation = states.filter((s) => s.kind === "simulation").length;
    return { configured, simulation, total: CHANNELS.length };
  }, [status.data]);

  return (
    <>
      <Header
        title="Configurações"
        subtitle="Centro de administração da instituição: o que está ativo, o que é somente leitura e para onde ir quando a gestão é especializada."
      />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-12 pt-5 md:px-9 md:pt-7">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Administração
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">
              {orgName || (me.isLoading ? "Carregando instituição…" : "Instituição")}
            </h2>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Dados vindos da API autenticada. Controles sem contrato de persistência permanecem
              somente leitura.
            </p>
          </div>
          {channelsSummary && (
            <p className="text-xs text-muted-foreground">
              Canais: {channelsSummary.configured} configurados · {channelsSummary.simulation} em
              simulação
            </p>
          )}
        </div>

        <Tabs
          value={section}
          onValueChange={(id) => setSection(id as SectionId)}
          items={SECTIONS.map((s) => ({ id: s.id, label: s.label }))}
        />

        <TabPanel when="instituicao" active={section} className="space-y-4">
          <SectionIntro
            icon={Building2}
            title="Instituição"
            description="Identidade e contexto da organização autenticada. Edição de nome e preferências regionais só aparece quando existir endpoint de atualização."
          />
          {me.isLoading && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Skeleton className="h-24 rounded-xl" />
              <Skeleton className="h-24 rounded-xl" />
            </div>
          )}
          {me.isError && (
            <ErrorBanner message="Não foi possível carregar o perfil da instituição (GET /org/me)." />
          )}
          {me.data && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Dados da organização</CardTitle>
                <CardDescription>Somente leitura — origem: sessão autenticada.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                <Datum label="Nome" value={me.data.tenant_name || "—"} />
                <Datum label="Identificador (slug)" value={me.data.tenant_slug || "—"} />
                <Datum label="Seu perfil de acesso" value={String(roleLabel)} />
                <Datum
                  label="Onboarding"
                  value={
                    me.data.onboarding_completed
                      ? `Concluído${me.data.onboarding_completed_at ? ` · ${new Date(me.data.onboarding_completed_at).toLocaleDateString("pt-BR")}` : ""}`
                      : "Pendente"
                  }
                />
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Membros e convites</CardTitle>
              <CardDescription>
                Gestão de pessoas e papéis fica na área dedicada — não duplicamos o fluxo aqui.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Link href="/membros">
                <Button type="button" variant="outline" size="sm">
                  <Users className="h-4 w-4" /> Abrir membros
                </Button>
              </Link>
            </CardContent>
          </Card>
        </TabPanel>

        <TabPanel when="comunicacao" active={section} className="space-y-4">
          <SectionIntro
            icon={MessageCircle}
            title="Comunicação"
            description="Estado dos canais de retenção conforme o ambiente (GET /agents/status). Configuração de credenciais e conectores de dados é especializada."
          />
          {status.isLoading && (
            <div className="grid gap-3 sm:grid-cols-3">
              {CHANNELS.map((c) => (
                <Skeleton key={c.key} className="h-[100px] rounded-xl" />
              ))}
            </div>
          )}
          {status.isError && (
            <ErrorBanner message="Não foi possível consultar o estado dos canais." />
          )}
          {status.data && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "rounded-full px-3 py-1.5 text-[10px] font-semibold",
                    status.data.dry_run_default
                      ? "bg-[#eef0ff] text-[#3848b5]"
                      : "bg-[#fff0ed] text-[#b84336]"
                  )}
                >
                  {status.data.dry_run_default
                    ? "Simulação padrão no ambiente"
                    : "Modo real padrão no ambiente"}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  Flag de ambiente — não editável por tenant nesta versão.
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {CHANNELS.map(({ key, name, icon: Icon }) => {
                  const st = channelState(status.data.providers?.[key]);
                  return (
                    <Card key={key} className="border-border/80">
                      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="grid h-9 w-9 place-items-center rounded-xl bg-secondary text-primary">
                            <Icon className="h-4 w-4" />
                          </span>
                          <CardTitle className="text-sm">{name}</CardTitle>
                        </div>
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                            stateBadgeClass(st.kind)
                          )}
                        >
                          {st.label}
                        </span>
                      </CardHeader>
                      <CardContent>
                        <p className="text-xs leading-relaxed text-muted-foreground">{st.detail}</p>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Dados e integrações</CardTitle>
                  <CardDescription>
                    Importações, catálogo de conectores e ingestão JSON — gestão especializada.
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                  <Link href="/conectores">
                    <Button type="button" size="sm" variant="outline">
                      <Plug className="h-4 w-4" /> Abrir dados e integrações
                    </Button>
                  </Link>
                  <Link href="/importar">
                    <Button type="button" size="sm" variant="ghost">
                      <ExternalLink className="h-4 w-4" /> Importar planilhas
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            </>
          )}
        </TabPanel>

        <TabPanel when="regras" active={section} className="space-y-4">
          <SectionIntro
            icon={Settings2}
            title="Regras operacionais"
            description="Parâmetros de anti-spam e fila lidos do ambiente. Não há endpoint de atualização por instituição — não exibimos switches sem efeito."
          />
          {status.isLoading && <Skeleton className="h-40 w-full rounded-xl" />}
          {status.isError && (
            <ErrorBanner message="Não foi possível carregar as regras operacionais." />
          )}
          {status.data && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Anti-spam e fila</CardTitle>
                <CardDescription>
                  Valores aplicados pelo backend a todos os tenants deste deploy. Somente leitura.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Datum
                  label="Intervalo mínimo entre contatos"
                  value={`${status.data.anti_spam.min_hours_between_contact} horas`}
                />
                <Datum
                  label="Máximo de contatos por semana"
                  value={`${status.data.anti_spam.max_contacts_per_week} / aluno`}
                />
                <Datum label="Fila de retenção" value={status.data.queue?.name || "—"} />
                <Datum
                  label="Fila dead-letter"
                  value={status.data.queue?.dead_letter_name || "—"}
                />
                <Datum
                  label="Tentativas máximas"
                  value={
                    status.data.queue?.max_attempts != null
                      ? String(status.data.queue.max_attempts)
                      : "—"
                  }
                />
                <Datum
                  label="Backoff de retry"
                  value={
                    status.data.queue?.retry_backoff_seconds != null
                      ? `${status.data.queue.retry_backoff_seconds}s`
                      : "—"
                  }
                />
              </CardContent>
            </Card>
          )}
          <p className="flex items-start gap-2 rounded-xl bg-muted/40 p-3 text-[11px] leading-relaxed text-muted-foreground">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            Preferências de comunicação por aluno (opt-out, canais, tópicos) são geridas na ficha do
            aluno, não nesta tela institucional.
          </p>
        </TabPanel>

        <TabPanel when="inteligencia" active={section} className="space-y-4">
          <SectionIntro
            icon={BrainCircuit}
            title="Inteligência"
            description="Transparência sobre o modelo preditivo ativo. Treinamento e ativação de modelos não são alteráveis nesta tela (governança da MIRA Base)."
          />
          {model.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}
          {model.isError && (
            <ErrorBanner message="Informações do modelo indisponíveis no momento." />
          )}
          {model.data && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Modelo preditivo</CardTitle>
                <CardDescription>GET /model/info — somente leitura.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <Datum label="Status" value={model.data.status || "Indisponível"} />
                  <Datum label="Versão" value={model.data.version || "—"} />
                  <Datum label="Escopo" value={model.data.model_scope || "—"} />
                  <Datum label="Dados de treino" value={model.data.training_data || "—"} />
                  {typeof model.data.auc === "number" && (
                    <Datum label="AUC informado" value={model.data.auc.toFixed(3)} />
                  )}
                </div>
                <p className="rounded-xl border border-[#dce0ff] bg-[#f3f4ff] p-3 text-xs leading-relaxed text-[#313e9e]">
                  {model.data.disclaimer || copy.modelDisclaimerFallback}
                </p>
              </CardContent>
            </Card>
          )}
        </TabPanel>

        <TabPanel when="seguranca" active={section} className="space-y-4">
          <SectionIntro
            icon={ShieldCheck}
            title="Segurança"
            description="Sessão neste navegador e perfil de acesso. Gestão de membros e convites permanece em /membros."
          />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sessão atual</CardTitle>
              <CardDescription>
                Token armazenado apenas neste dispositivo, vinculado à instituição autenticada.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {me.isLoading && <Skeleton className="h-16 w-full" />}
              {me.isError && (
                <ErrorBanner message="Não foi possível carregar os dados da sessão." />
              )}
              {me.data && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Datum label="Nome de exibição" value={me.data.display_name || "—"} />
                  <Datum label="E-mail" value={me.data.email || "—"} />
                  <Datum label="Papel (RBAC)" value={String(me.data.role || "—")} />
                  <Datum label="Instituição" value={me.data.tenant_name || "—"} />
                </div>
              )}
              <Button type="button" variant="outline" onClick={logout}>
                <LogOut className="h-4 w-4" /> Sair e limpar sessão
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Autenticação multifator (MFA)</CardTitle>
              <CardDescription>Proteja sua conta com um aplicativo autenticador compatível com TOTP.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {mfaStatus.isLoading && <Skeleton className="h-16 w-full" />}
              {mfaStatus.isError && <ErrorBanner message="Não foi possível consultar o estado do MFA." />}
              {mfaStatus.data && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-muted/35 p-3">
                  <div><p className="text-sm font-semibold">{mfaStatus.data.enabled ? "MFA ativado" : "MFA desativado"}</p><p className="text-xs text-muted-foreground">{mfaStatus.data.enabled ? `${mfaStatus.data.recovery_codes_remaining} códigos de recuperação disponíveis` : "Adicione uma camada extra de proteção à sua conta."}</p></div>
                  <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", mfaStatus.data.enabled ? "bg-emerald-50 text-emerald-700" : "bg-muted text-muted-foreground")}>{mfaStatus.data.enabled ? "Protegida" : "Não configurado"}</span>
                </div>
              )}
              {mfaError && <ErrorBanner message={mfaError} />}
              {mfaMessage && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800">{mfaMessage}</p>}
              {mfaEnrollment && (
                <div className="space-y-3 rounded-xl border p-4">
                  <p className="text-sm font-medium">1. Escaneie o QR Code no aplicativo autenticador</p>
                  <img src={mfaEnrollment.qr_code} alt="QR Code para configurar MIRA no aplicativo autenticador" className="mx-auto h-48 w-48" />
                  <p className="break-all rounded-lg bg-muted p-2 font-mono text-xs">{mfaEnrollment.secret}</p>
                  <p className="text-xs text-muted-foreground">2. Digite o código de 6 dígitos gerado pelo aplicativo para confirmar.</p>
                  <Input value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0,6))} inputMode="numeric" placeholder="000000" maxLength={6} />
                  <Button onClick={confirmMfaEnrollment} disabled={mfaCode.length !== 6}>Confirmar e ativar MFA</Button>
                </div>
              )}
              {recoveryCodes && (
                <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <p className="text-sm font-semibold text-amber-900">Guarde estes códigos agora</p>
                  <p className="text-xs text-amber-800">Cada código pode ser usado uma única vez. Eles não serão exibidos novamente.</p>
                  <div className="grid grid-cols-2 gap-2">{recoveryCodes.map((code) => <code key={code} className="rounded bg-white p-2 text-center text-xs">{code}</code>)}</div>
                  <Button variant="outline" onClick={() => navigator.clipboard.writeText(recoveryCodes.join("\n"))}>Copiar códigos</Button>
                  <Button variant="ghost" onClick={() => setRecoveryCodes(null)}>Já guardei</Button>
                </div>
              )}
              {!mfaEnrollment && !recoveryCodes && !mfaStatus.data?.enabled && <Button onClick={startMfaEnrollment}>Configurar aplicativo autenticador</Button>}
              {mfaStatus.data?.enabled && (
                <div className="space-y-3">
                  <label className="text-xs font-medium" htmlFor="mfa-management-code">Confirme sua identidade com o código atual</label>
                  <Input id="mfa-management-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, "").slice(0,6))} inputMode="numeric" placeholder="Código de 6 dígitos" maxLength={6} />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" onClick={regenerateRecoveryCodes} disabled={mfaCode.length !== 6}>Gerar novos códigos</Button>
                    <Button variant="destructive" onClick={disableMfa} disabled={mfaCode.length !== 6}>Desativar MFA</Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          <p className="text-xs text-muted-foreground">
            Permissões de API são aplicadas no backend (RBAC + tenant_id). A interface não substitui
            essa validação.
          </p>
        </TabPanel>
      </main>
    </>
  );
}

function SectionIntro({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary">
        <Icon className="h-4 w-4" />
      </span>
      <div>
        <h3 className="text-base font-semibold tracking-tight">{title}</h3>
        <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

function Datum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-muted/35 p-3">
      <p className="text-[10px] font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-xs font-semibold" title={value}>
        {value}
      </p>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]"
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
