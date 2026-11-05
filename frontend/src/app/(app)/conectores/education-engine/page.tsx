"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft, AlertCircle, CheckCircle2, Database, History, LockKeyhole,
  Plug, RefreshCw, ShieldCheck, GraduationCap, Wallet,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { educationEngine, type EducationEngineConnection } from "@/lib/education-engine-api";

const statusCopy: Record<string, string> = {
  not_configured: "Não configurado",
  configured: "Aguardando verificação",
  verified: "Verificado",
  disabled: "Desativado",
  error: "Falha na verificação",
};

const eventCopy: Record<string, string> = {
  connection_configured: "Configuração salva",
  connection_verified: "Acesso ao motor verificado",
  connection_verification_failed: "Falha ao verificar acesso",
  connection_enabled: "Conexão habilitada",
  connection_disabled: "Conexão desabilitada",
  student_link_created: "Vínculo de aluno criado",
};

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Não foi possível concluir esta operação.";
}

function dateLabel(value?: string | null): string {
  if (!value) return "Ainda não registrado";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Data indisponível"
    : date.toLocaleString("pt-BR", { dateStyle: "medium", timeStyle: "short" });
}

function ConnectionState({ data }: { data: EducationEngineConnection }) {
  const active = data.environment_enabled && data.enabled && data.status === "verified";
  const label = !data.environment_enabled
    ? "Aguardando infraestrutura"
    : active ? "Conexão ativa" : statusCopy[data.status] ?? "Estado desconhecido";
  return (
    <span className={
      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold " +
      (active
        ? "border-[#ABEFC6] bg-[#ECFDF3] text-[#067647]"
        : "border-[#E4E7EC] bg-[#F9FAFB] text-[#475467]")
    }>
      <span aria-hidden="true" className={
        "h-1.5 w-1.5 rounded-full " + (active ? "bg-[#079455]" : "bg-[#98A2B3]")
      } />
      {label}
    </span>
  );
}

function Stage({
  number, title, description, done,
}: { number: number; title: string; description: string; done: boolean }) {
  return (
    <div className="flex min-w-0 items-start gap-3">
      <div className={
        "grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[12px] font-semibold " +
        (done ? "bg-[#ECFDF3] text-[#067647]" : "bg-[#F2F4F7] text-[#667085]")
      }>
        {done ? <CheckCircle2 className="h-4 w-4" /> : number}
      </div>
      <div>
        <p className="text-[13px] font-semibold text-[#101828]">{title}</p>
        <p className="mt-0.5 text-[12px] leading-5 text-[#667085]">{description}</p>
      </div>
    </div>
  );
}

export default function EducationEngineIntegrationPage() {
  const queryClient = useQueryClient();
  const [site, setSite] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [confirmDisable, setConfirmDisable] = useState(false);

  const connection = useQuery({
    queryKey: ["education-engine", "connection"],
    queryFn: educationEngine.connection,
    retry: false,
  });
  const audit = useQuery({
    queryKey: ["education-engine", "audit"],
    queryFn: () => educationEngine.audit(30),
    enabled: connection.data?.configured === true,
    retry: false,
  });
  useEffect(() => {
    if (connection.data?.site_name) setSite(connection.data.site_name);
  }, [connection.data?.site_name]);

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["education-engine"] });
  }
  const configure = useMutation({
    mutationFn: () => educationEngine.configure({
      site_name: site.trim(), api_key: apiKey.trim(), api_secret: apiSecret.trim(),
    }),
    onSuccess: () => {
      setApiKey("");
      setApiSecret("");
      setConfirmDisable(false);
      toast.success("Configuração salva. Verifique a conexão antes de ativar.");
      refresh();
    },
    onError: (error) => toast.error(describeError(error)),
  });
  const verify = useMutation({
    mutationFn: educationEngine.verify,
    onSuccess: () => {
      toast.success("Credenciais verificadas. A conexão ainda não está habilitada.");
      refresh();
    },
    onError: (error) => { toast.error(describeError(error)); refresh(); },
  });
  const enable = useMutation({
    mutationFn: educationEngine.enable,
    onSuccess: () => { toast.success("Conexão acadêmica habilitada para esta IES."); refresh(); },
    onError: (error) => toast.error(describeError(error)),
  });
  const disable = useMutation({
    mutationFn: educationEngine.disable,
    onSuccess: () => {
      setConfirmDisable(false);
      toast.success("Conexão desabilitada.");
      refresh();
    },
    onError: (error) => toast.error(describeError(error)),
  });

  const data = connection.data;
  const isBusy = configure.isPending || verify.isPending || enable.isPending || disable.isPending;
  const ready = data?.environment_enabled === true;
  const verified = data?.status === "verified";
  const active = ready && verified && data?.enabled === true;

  return (
    <>
      <Header title="Motor acadêmico" compact />
      <main className="mira-page mx-auto w-full max-w-[1120px] space-y-6 px-4 pb-12 pt-6 md:px-8 md:pt-8">
        <nav aria-label="Localização" className="flex items-center gap-2 text-[12px] text-[#667085]">
          <Link href="/conectores" className="inline-flex items-center gap-1.5 hover:text-[#266DF0]">
            <ArrowLeft className="h-3.5 w-3.5" />
            Integrações
          </Link>
          <span aria-hidden="true">/</span>
          <span className="font-medium text-[#344054]">Motor acadêmico MIRA</span>
        </nav>

        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#E4E7EC] pb-6">
          <div className="flex items-start gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-[12px] border border-[#E4E7EC] bg-white text-[#266DF0] shadow-sm">
              <GraduationCap className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-[24px] font-semibold tracking-[-0.035em] text-[#101828]">Motor acadêmico MIRA</h1>
              <p className="mt-1.5 max-w-[640px] text-[13px] leading-6 text-[#667085]">
                Centralize registros acadêmicos e financeiros da instituição, mantendo
                seus dados, permissões e operação dentro da MIRA.
              </p>
            </div>
          </div>
          {data && <ConnectionState data={data} />}
        </div>

        {connection.isLoading && (
          <div className="rounded-xl border border-[#E4E7EC] bg-white p-7 text-[13px] text-[#667085]">
            Consultando configuração da instituição…
          </div>
        )}
        {connection.isError && (
          <div role="alert" className="flex gap-3 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-5">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-[#B54708]" />
            <div>
              <p className="text-[13px] font-semibold text-[#93370D]">Motor acadêmico ainda não disponível neste ambiente</p>
              <p className="mt-1 text-[12px] leading-5 text-[#93370D]">
                O módulo depende da API MIRA e da instalação privada do motor Frappe. Nenhum dado foi simulado.
              </p>
              <p className="mt-2 text-[11px] text-[#B54708]">{describeError(connection.error)}</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => void connection.refetch()}>
                <RefreshCw className="h-3.5 w-3.5" /> Tentar novamente
              </Button>
            </div>
          </div>
        )}

        {data && (
          <>
            {!ready && (
              <div role="status" className="flex gap-3 rounded-[10px] border border-[#E4E7EC] bg-[#F9FAFB] p-4">
                <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-[#667085]" />
                <p className="text-[12px] leading-5 text-[#475467]">
                  O serviço privado ainda não foi homologado e habilitado no Render.
                  As operações abaixo permanecem bloqueadas até a liberação técnica.
                </p>
              </div>
            )}

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(260px,1fr)]">
              <section className="rounded-[12px] border border-[#E4E7EC] bg-white p-5 shadow-[0_1px_3px_rgba(16,24,40,.04)] md:p-6">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-[15px] font-semibold text-[#101828]">Configuração da instituição</h2>
                    <p className="mt-1 text-[12px] leading-5 text-[#667085]">
                      Cada instituição usa seu próprio site e suas credenciais de acesso restrito.
                    </p>
                  </div>
                  <Plug className="h-4 w-4 shrink-0 text-[#98A2B3]" />
                </div>

                <form
                  className="mt-6 space-y-4"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!isBusy && ready) configure.mutate();
                  }}
                >
                  <div>
                    <label htmlFor="education-site" className="mb-1.5 block text-[12px] font-medium text-[#344054]">
                      Site da instituição
                    </label>
                    <input
                      id="education-site"
                      type="text"
                      required
                      value={site}
                      disabled={!ready || isBusy || (data.configured && Boolean(data.site_name))}
                      onChange={(e) => setSite(e.target.value)}
                      placeholder="ies-a.interno.example"
                      autoComplete="off"
                      className="h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-[13px] text-[#101828] outline-none focus:border-[#266DF0] focus:ring-2 focus:ring-[#266DF0]/15 disabled:bg-[#F9FAFB] disabled:text-[#667085]"
                    />
                    <p className="mt-1 text-[11px] text-[#98A2B3]">
                      O site precisa estar previamente autorizado na configuração do Render.
                    </p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label htmlFor="education-key" className="mb-1.5 block text-[12px] font-medium text-[#344054]">
                        Chave de API
                      </label>
                      <input
                        id="education-key"
                        type="password"
                        required
                        value={apiKey}
                        disabled={!ready || isBusy}
                        onChange={(e) => setApiKey(e.target.value)}
                        minLength={8}
                        autoComplete="new-password"
                        placeholder="Nova chave"
                        className="h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-[13px] outline-none focus:border-[#266DF0] focus:ring-2 focus:ring-[#266DF0]/15 disabled:bg-[#F9FAFB]"
                      />
                    </div>
                    <div>
                      <label htmlFor="education-secret" className="mb-1.5 block text-[12px] font-medium text-[#344054]">
                        Segredo de API
                      </label>
                      <input
                        id="education-secret"
                        type="password"
                        required
                        value={apiSecret}
                        disabled={!ready || isBusy}
                        onChange={(e) => setApiSecret(e.target.value)}
                        minLength={8}
                        autoComplete="new-password"
                        placeholder="Novo segredo"
                        className="h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-[13px] outline-none focus:border-[#266DF0] focus:ring-2 focus:ring-[#266DF0]/15 disabled:bg-[#F9FAFB]"
                      />
                    </div>
                  </div>
                  <p className="flex items-center gap-1.5 text-[11px] text-[#667085]">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    As credenciais ficam cifradas na API MIRA e nunca são retornadas à interface.
                  </p>
                  <div className="flex flex-wrap gap-2 pt-2">
                    <Button type="submit" disabled={!ready || isBusy || !site.trim() || !apiKey.trim() || !apiSecret.trim()}>
                      {configure.isPending ? "Salvando…" : data.configured ? "Atualizar credenciais" : "Salvar conexão"}
                    </Button>
                    {data.configured && (
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!ready || isBusy || active}
                        onClick={() => verify.mutate()}
                      >
                        {verify.isPending ? "Verificando…" : "Verificar acesso"}
                      </Button>
                    )}
                  </div>
                </form>
              </section>

              <div className="space-y-4">
                <section className="rounded-[12px] border border-[#E4E7EC] bg-white p-5">
                  <h2 className="text-[14px] font-semibold text-[#101828]">Ativação segura</h2>
                  <div className="mt-5 space-y-5">
                    <Stage
                      number={1} title="Conectar o site"
                      description="Definir a identidade da IES e as credenciais restritas."
                      done={data.configured}
                    />
                    <Stage
                      number={2} title="Verificar acesso"
                      description="Confirmar que o serviço acadêmico reconhece a conta."
                      done={verified}
                    />
                    <Stage
                      number={3} title="Habilitar"
                      description="Disponibilizar as consultas somente leitura dentro da MIRA."
                      done={active}
                    />
                  </div>
                  <div className="mt-6 border-t border-[#E4E7EC] pt-4">
                    {verified && !active && (
                      <Button className="w-full" disabled={!ready || isBusy} onClick={() => enable.mutate()}>
                        {enable.isPending ? "Ativando…" : "Habilitar conexão"}
                      </Button>
                    )}
                    {active && (
                      <>
                        <label className="flex items-center gap-2 text-[12px] text-[#475467]">
                          <input
                            type="checkbox"
                            checked={confirmDisable}
                            onChange={(e) => setConfirmDisable(e.target.checked)}
                            className="accent-[#266DF0]"
                          />
                          Confirmo que desejo interromper as consultas
                        </label>
                        <Button
                          variant="outline"
                          className="mt-3 w-full"
                          disabled={!confirmDisable || isBusy}
                          onClick={() => disable.mutate()}
                        >
                          {disable.isPending ? "Desabilitando…" : "Desabilitar conexão"}
                        </Button>
                      </>
                    )}
                    {!verified && !active && (
                      <p className="text-[12px] leading-5 text-[#667085]">
                        A conexão só pode ser habilitada após uma verificação recente.
                      </p>
                    )}
                  </div>
                </section>

                <section className="rounded-[12px] border border-[#E4E7EC] bg-white p-5">
                  <div className="flex items-center gap-2">
                    <History className="h-4 w-4 text-[#667085]" />
                    <h2 className="text-[14px] font-semibold text-[#101828]">Atividade da conexão</h2>
                  </div>
                  {audit.isLoading && <p className="mt-4 text-[12px] text-[#667085]">Carregando atividades…</p>}
                  {audit.isError && <p className="mt-4 text-[12px] text-[#667085]">Auditoria indisponível.</p>}
                  {!audit.isLoading && !audit.isError && (audit.data?.events.length ?? 0) === 0 && (
                    <p className="mt-4 text-[12px] text-[#667085]">Nenhuma atividade registrada.</p>
                  )}
                  <ol className="mt-4 space-y-3">
                    {(audit.data?.events ?? []).slice(0, 8).map((event, index) => (
                      <li key={event.event_type + event.occurred_at + index} className="border-l-2 border-[#E4E7EC] py-0.5 pl-3">
                        <p className="text-[12px] font-medium text-[#344054]">
                          {eventCopy[event.event_type] ?? "Atividade administrativa"}
                        </p>
                        <p className="mt-0.5 text-[11px] text-[#98A2B3]">{dateLabel(event.occurred_at)}</p>
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
            </div>

            <section className="rounded-[12px] border border-[#E4E7EC] bg-white p-5 md:p-6">
              <h2 className="text-[15px] font-semibold text-[#101828]">Recursos disponíveis após a conexão</h2>
              <p className="mt-1 text-[12px] text-[#667085]">
                Os dados vêm do motor próprio da MIRA. A edição e a conciliação financeira não estão habilitadas nesta etapa.
              </p>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                {[
                  { title: "Acadêmico", description: "Matrículas, frequência e notas", icon: GraduationCap },
                  { title: "Financeiro", description: "Mensalidades e valores de origem, sem confirmação de quitação", icon: Wallet },
                  { title: "Governança", description: "Vínculo por aluno, isolamento institucional e auditoria", icon: Database },
                ].map(({ title, description, icon: Icon }) => (
                  <div key={title} className="rounded-lg border border-[#EAECF0] bg-[#FCFCFD] p-4">
                    <Icon className="h-4 w-4 text-[#266DF0]" />
                    <h3 className="mt-3 text-[13px] font-semibold text-[#344054]">{title}</h3>
                    <p className="mt-1 text-[12px] leading-5 text-[#667085]">{description}</p>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
    </>
  );
}
