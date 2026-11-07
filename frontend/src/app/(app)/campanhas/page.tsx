"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ObjectIndex, initialObjectIndexState } from "@/components/object-index/object-index";
import { RecordDrawer } from "@/components/record/record-drawer";
import { RecordProperties } from "@/components/record/record-properties";
import { RecordRelations } from "@/components/record/record-relations";
import { RecordActivity } from "@/components/record/record-activity";
import { RecordSections } from "@/components/record/record-sections";
import { getVisibleNavigation } from "@/components/layout/navigation";
import type { ObjectField } from "@/components/object-index/object-index-types";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  FileCheck2,
  History,
  LockKeyhole,
  ShieldCheck,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { RetentionCampaignProposal } from "@/types/api";

const statusLabels: Record<string, string> = {
  draft: "Rascunho",
  in_review: "Em revisão",
  changes_requested: "Ajustes solicitados",
  approved: "Aprovada",
  scheduled: "Agendada",
  running: "Em execução simulada",
  paused: "Pausada",
  completed: "Concluída",
  cancelled: "Cancelada",
  failed: "Falhou",
};

const channelLabels: Record<string, string> = {
  email: "E-mail",
  whatsapp: "WhatsApp",
  sms: "SMS",
  operacao_interna: "Operação interna",
};

function localDateTimeToUtcIso(value: string, timeZone: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Informe uma data e hora válidas.");
  const [, year, month, day, hour, minute] = match;
  const desired = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  let candidate = desired;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = Object.fromEntries(
      formatter.formatToParts(new Date(candidate)).map((part) => [part.type, part.value])
    );
    const represented = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour), Number(parts.minute), Number(parts.second)
    );
    candidate += desired - represented;
  }
  const check = Object.fromEntries(
    formatter.formatToParts(new Date(candidate)).map((part) => [part.type, part.value])
  );
  if (
    Number(check.year) !== Number(year) || Number(check.month) !== Number(month) ||
    Number(check.day) !== Number(day) || Number(check.hour) !== Number(hour) ||
    Number(check.minute) !== Number(minute)
  ) {
    throw new Error("Este horário local não existe no fuso selecionado. Escolha outro horário.");
  }
  const localAsUtc = Date.UTC(
    Number(check.year), Number(check.month) - 1, Number(check.day),
    Number(check.hour), Number(check.minute), Number(check.second)
  );
  const offsetMinutes = Math.round((localAsUtc - candidate) / 60000);
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absoluteOffset = Math.abs(offsetMinutes);
  const offset = `${sign}${String(Math.floor(absoluteOffset / 60)).padStart(2, "0")}:${String(absoluteOffset % 60).padStart(2, "0")}`;
  return `${value}:00${offset}`;
}

const CAMPAIGN_INDEX_FIELDS: ObjectField<RetentionCampaignProposal>[] = [
  { key: "title", title: "Campanha", type: "text", primary: true, width: 260,
    getValue: item => item.title, filterable: true, sortable: true },
  { key: "status", title: "Estado", type: "status", width: 130,
    getValue: item => item.status, filterable: true,
    options: [
      { value: "draft", label: "Rascunho" }, { value: "in_review", label: "Em revisão" },
      { value: "approved", label: "Aprovada" }, { value: "scheduled", label: "Agendada" },
      { value: "completed", label: "Concluída" }, { value: "failed", label: "Falhou" },
    ],
    render: item => <span className="mira-tag mira-tag--blue">{statusLabels[item.status] || item.status}</span> },
  { key: "objective", title: "Objetivo", type: "text", width: 225,
    getValue: item => item.objective, filterable: true },
  { key: "audience_total", title: "Público", type: "number", width: 95,
    getValue: item => item.audience_total, sortable: true },
  { key: "recommended_channels", title: "Canais", type: "multiselect", width: 165,
    getValue: item => item.recommended_channels },
  { key: "created_at", title: "Criada em", type: "datetime", width: 145,
    getValue: item => item.created_at, sortable: true },
];

function CampaignProposalsContent() {
  const searchParams = useSearchParams();
  const requestedProposal = searchParams.get("proposal");
  const queryClient = useQueryClient();
  const proposalsQuery = useQuery({
    queryKey: ["retention-campaign-proposals"],
    queryFn: () => api.retentionCampaignProposals(),
  });
  const meQuery = useQuery({ queryKey: ["org-me"], queryFn: () => api.me() });
  const scheduleQuery = useQuery({
    queryKey: ["retention-campaign-schedule"],
    queryFn: () => api.retentionCampaignSchedule(),
  });
  const proposals = proposalsQuery.data?.proposals ?? [];
  const [selectedId, setSelectedId] = useState("");
  const [previewId, setPreviewId] = useState<string|null>(null);
  useEffect(() => {
    // Search results only select/read an existing proposal, never mutate/approve it.
    if (requestedProposal && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestedProposal)) {
      setSelectedId(requestedProposal);
      setPreviewId(requestedProposal);
    }
  }, [requestedProposal]);
  const [objectIndexState, setObjectIndexState] = useState(() => initialObjectIndexState(CAMPAIGN_INDEX_FIELDS));
  const selected = proposals.find((item) => item.id === selectedId) ?? null;
  const previewProposal = proposals.find(item => item.id === previewId) ?? null;
  const canSeeGroups = getVisibleNavigation(meQuery.data).some(group=>group.items.some(item=>item.href==="/alunos/grupos"));
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [strategy, setStrategy] = useState("");
  const [messageBrief, setMessageBrief] = useState("");
  const [channels, setChannels] = useState<string[]>([]);
  const [cadence, setCadence] = useState("0, 3");
  const [reviewNote, setReviewNote] = useState("");
  const [authorizationBasis, setAuthorizationBasis] = useState("");
  const [authorizationReference, setAuthorizationReference] = useState("");
  const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTimezone, setScheduleTimezone] = useState("America/Sao_Paulo");

  const role = meQuery.data?.role ?? "viewer";
  const userId = meQuery.data?.user_id ?? null;
  const canCoordinate = role === "coordinator" || role === "admin";
  const isAdmin = role === "admin";

  useEffect(() => {
    if (!selectedId && proposals.length) setSelectedId(proposals[0].id);
  }, [selectedId, proposals]);

  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title);
    setObjective(selected.objective);
    setStrategy(selected.strategy);
    setMessageBrief(selected.message_brief);
    setChannels(selected.recommended_channels);
    setCadence(selected.cadence_days.join(", "));
    setReviewNote("");
    setAuthorizationBasis(selected.authorization_basis ?? "");
    setAuthorizationReference(selected.authorization_reference ?? "");
    setAttested(false);
  }, [selected]);

  const auditQuery = useQuery({
    queryKey: ["retention-campaign-proposal-audit", selectedId],
    queryFn: () => api.retentionCampaignProposalAudit(selectedId),
    enabled: Boolean(selectedId) && canCoordinate,
    retry: false,
  });

  const editable = Boolean(
    selected && canCoordinate && ["draft", "changes_requested"].includes(selected.status)
  );
  const isCreator = Boolean(selected && userId && selected.created_by === userId);
  const canReview = Boolean(selected && editable && !isCreator);
  const inReview = selected?.status === "in_review";
  const canRequestChanges = Boolean(inReview && canCoordinate && !isCreator);
  const canAttest = Boolean(inReview && isAdmin && !isCreator);
  const canSchedule = Boolean(selected?.status === "approved" && isAdmin);
  const isScheduled = selected?.status === "scheduled";
  const canApprove = Boolean(
    inReview && isAdmin && !isCreator && selected?.authorization_status === "institution_attested"
  );

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["retention-campaign-proposals"] });
    await queryClient.invalidateQueries({ queryKey: ["retention-campaign-proposal-audit", selectedId] });
    await queryClient.invalidateQueries({ queryKey: ["retention-campaign-schedule"] });
  };

  async function perform(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível concluir a ação.");
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    if (!selected) return;
    const parsedCadence = cadence
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean)
      .map(Number);
    if (parsedCadence.some((day) => !Number.isInteger(day))) {
      toast.error("Informe a cadência como dias separados por vírgula.");
      return;
    }
    await perform(
      () => api.updateRetentionCampaignProposal(selected.id, {
        title, objective, strategy, message_brief: messageBrief,
        recommended_channels: channels, cadence_days: parsedCadence,
      }),
      "Proposta atualizada. A revisão anterior foi invalidada."
    );
  }

  const auditEvents = auditQuery.data?.events ?? [];
  const audienceSummary = useMemo(() => {
    if (!selected) return [];
    return [
      { label: "Público único", value: selected.audience_total },
      { label: "Elegíveis tecnicamente", value: selected.outreach_eligible_count },
      { label: "Bloqueados", value: selected.blocked_count },
      { label: "Ação interna", value: selected.internal_action_count },
    ];
  }, [selected]);

  return (
    <>
      <Header
        title="Campanhas inteligentes"
        subtitle="Edite propostas, encaminhe para revisão e acompanhe aprovações. Nenhuma campanha é enviada nesta etapa."
      />
      <main className="mx-auto w-full max-w-7xl space-y-6 px-4 pb-12 pt-5 md:px-9 md:pt-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-muted-foreground">
              {proposalsQuery.data?.count ?? 0} propostas persistidas
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900">
            <LockKeyhole className="h-4 w-4" />
            Agendamento manual disponível para propostas aprovadas · execução desabilitada
          </div>
        </div>

        {proposalsQuery.isLoading ? (
          <Card><CardContent className="p-6 text-sm text-muted-foreground">Carregando propostas…</CardContent></Card>
        ) : proposalsQuery.isError ? (
          <Card><CardContent className="p-6 text-sm text-red-600">Não foi possível carregar as propostas. Verifique sua permissão.</CardContent></Card>
        ) : proposals.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
              <FileCheck2 className="h-8 w-8 text-muted-foreground" />
              <h2 className="font-semibold">Nenhuma proposta disponível</h2>
              <p className="max-w-lg text-sm text-muted-foreground">
                As propostas criadas pela inteligência de campanhas aparecerão aqui para edição e revisão.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-5">
            <ObjectIndex
              objectKey="campaigns" title="Propostas de campanhas"
              description="Revisão e aprovação institucional; esta listagem não representa execuções de disparo."
              fields={CAMPAIGN_INDEX_FIELDS}
              rows={proposals}
              state={objectIndexState}
              onStateChange={setObjectIndexState}
              defaultViews={[
                { id: "todos", title: "Todas" },
                { id: "in_review", title: "Em revisão", filterKey: "status:in_review" },
                { id: "approved", title: "Aprovadas", filterKey: "status:approved" },
              ]}
              partial={typeof proposalsQuery.data?.count === "number" && proposalsQuery.data.count > proposals.length}
              total={proposalsQuery.data?.count}
              onOpen={proposal => { setSelectedId(proposal.id); setPreviewId(proposal.id); }}
              onRefresh={() => void proposalsQuery.refetch()}
              refreshing={proposalsQuery.isFetching}
              emptyTitle="Nenhuma proposta corresponde aos filtros."
            />

            {selected ? (
              <div className="space-y-5">
                <Card>
                  <CardHeader>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <CardTitle>{selected.title}</CardTitle>
                        <CardDescription className="mt-1">
                          Criada em {new Date(selected.created_at).toLocaleString("pt-BR")} · Revisão {selected.revision}
                        </CardDescription>
                      </div>
                      <span className="rounded-full bg-muted px-3 py-1.5 text-xs font-semibold">
                        {statusLabels[selected.status]}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      {audienceSummary.map((item) => (
                        <div key={item.label} className="rounded-lg border bg-muted/20 p-3">
                          <p className="text-xs text-muted-foreground">{item.label}</p>
                          <p className="mt-1 text-xl font-semibold tabular-nums">{item.value.toLocaleString("pt-BR")}</p>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 text-sm text-blue-950">
                      <div className="flex items-center gap-2 font-semibold">
                        <ShieldCheck className="h-4 w-4" /> Snapshot protegido
                      </div>
                      <p className="mt-1 text-xs">
                        Hash SHA-256: <code className="break-all">{selected.audience_hash}</code>
                      </p>
                      <p className="mt-1 text-xs">
                        A audiência, os grupos de origem e as contagens não são editáveis.
                      </p>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <label className="space-y-1.5 text-sm font-medium">
                        Título
                        <Input value={title} disabled={!editable || busy} onChange={(event) => setTitle(event.target.value)} />
                      </label>
                      <label className="space-y-1.5 text-sm font-medium">
                        Objetivo
                        <Input value={objective} disabled={!editable || busy} onChange={(event) => setObjective(event.target.value)} />
                      </label>
                    </div>
                    <label className="block space-y-1.5 text-sm font-medium">
                      Estratégia
                      <textarea value={strategy} disabled={!editable || busy} onChange={(event) => setStrategy(event.target.value)} rows={3} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60" />
                    </label>
                    <label className="block space-y-1.5 text-sm font-medium">
                      Briefing da mensagem
                      <textarea value={messageBrief} disabled={!editable || busy} onChange={(event) => setMessageBrief(event.target.value)} rows={4} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60" />
                    </label>

                    <div className="space-y-2">
                      <p className="text-sm font-medium">Canais recomendados</p>
                      <div className="flex flex-wrap gap-3">
                        {Object.entries(channelLabels).map(([key, label]) => (
                          <label key={key} className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={channels.includes(key)}
                              disabled={!editable || busy}
                              onChange={(event) => setChannels((current) =>
                                event.target.checked ? [...current, key] : current.filter((item) => item !== key)
                              )}
                            />
                            {label}
                          </label>
                        ))}
                      </div>
                    </div>
                    <label className="block max-w-xs space-y-1.5 text-sm font-medium">
                      Cadência (dias separados por vírgula)
                      <Input value={cadence} disabled={!editable || busy} onChange={(event) => setCadence(event.target.value)} />
                    </label>

                    {editable ? (
                      <div className="flex flex-wrap gap-2 border-t pt-4">
                        <Button disabled={busy} onClick={saveDraft}>Salvar alterações</Button>
                        <Button
                          variant="outline"
                          disabled={busy || !canReview}
                          onClick={() => void perform(() => api.reviewRetentionCampaignProposal(selected.id), "Proposta enviada para revisão.")}
                        >
                          <Clock3 className="mr-2 h-4 w-4" /> Enviar para revisão
                        </Button>
                      </div>
                    ) : null}

                    {canRequestChanges ? (
                      <div className="space-y-2 border-t pt-4">
                        <label className="block space-y-1.5 text-sm font-medium">
                          Justificativa para solicitar ajustes
                          <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} rows={2} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
                        </label>
                        <Button
                          variant="outline"
                          disabled={busy || reviewNote.trim().length < 3}
                          onClick={() => void perform(
                            () => api.requestRetentionCampaignProposalChanges(selected.id, reviewNote.trim()),
                            "Ajustes solicitados ao criador."
                          )}
                        >
                          Solicitar ajustes
                        </Button>
                      </div>
                    ) : null}

                    {canAttest ? (
                      <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                        <div>
                          <p className="text-sm font-semibold">Autorização de comunicação</p>
                          <p className="text-xs text-muted-foreground">
                            O atestado registra a declaração da instituição e a referência documental. Não é validação jurídica automática.
                          </p>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="space-y-1.5 text-sm font-medium">
                            Base declarada
                            <Input value={authorizationBasis} onChange={(event) => setAuthorizationBasis(event.target.value)} />
                          </label>
                          <label className="space-y-1.5 text-sm font-medium">
                            Referência documental
                            <Input value={authorizationReference} onChange={(event) => setAuthorizationReference(event.target.value)} />
                          </label>
                        </div>
                        <label className="flex items-start gap-2 text-xs">
                          <input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} />
                          Confirmo que a instituição revisou e declarou a base de autorização para esta comunicação.
                        </label>
                        <Button
                          variant="outline"
                          disabled={busy || !attested || authorizationBasis.trim().length < 3 || authorizationReference.trim().length < 2}
                          onClick={() => void perform(
                            () => api.attestRetentionCampaignProposalAuthorization(selected.id, {
                              basis: authorizationBasis.trim(),
                              evidence_reference: authorizationReference.trim(),
                              attestation: true,
                            }),
                            "Atestado institucional registrado."
                          )}
                        >
                          Registrar atestado
                        </Button>
                      </div>
                    ) : null}

                    {canApprove ? (
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                        <p className="text-xs text-muted-foreground">A aprovação encerra a edição, mas não agenda nem envia mensagens.</p>
                        <Button disabled={busy} onClick={() => void perform(
                          () => api.approveRetentionCampaignProposal(selected.id),
                          "Proposta aprovada. Prepare a execução no motor compartilhado de disparos."
                        )}>
                          <CheckCircle2 className="mr-2 h-4 w-4" /> Aprovar proposta
                        </Button>
                      </div>
                    ) : null}

                    {canSchedule ? (
                      <div className="space-y-3 rounded-lg border p-4">
                        <div>
                          <p className="text-sm font-semibold">Agendar campanha</p>
                          <p className="text-xs text-muted-foreground">
                            O agendamento registra data e fuso. Não cria uma execução nem envia mensagens.
                          </p>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="space-y-1.5 text-sm font-medium">
                            Data e hora local
                            <Input type="datetime-local" value={scheduleDate} disabled={busy} onChange={(event) => setScheduleDate(event.target.value)} />
                          </label>
                          <label className="space-y-1.5 text-sm font-medium">
                            Fuso horário IANA
                            <Input value={scheduleTimezone} disabled={busy} onChange={(event) => setScheduleTimezone(event.target.value)} placeholder="America/Sao_Paulo" />
                          </label>
                        </div>
                        <Button
                          variant="outline"
                          disabled={busy || !scheduleDate || scheduleTimezone.trim().length < 3}
                          onClick={() => {
                            try {
                              const scheduledFor = localDateTimeToUtcIso(scheduleDate, scheduleTimezone.trim());
                              void perform(
                                () => api.scheduleRetentionCampaignProposal(selected.id, {
                                  scheduled_for: scheduledFor,
                                  schedule_timezone: scheduleTimezone.trim(),
                                }),
                                "Agendamento registrado. Nenhuma execução foi iniciada."
                              );
                            } catch (error) {
                              toast.error(error instanceof Error ? error.message : "Data ou fuso inválido.");
                            }
                          }}
                        >
                          <Clock3 className="mr-2 h-4 w-4" /> Confirmar agendamento
                        </Button>
                      </div>
                    ) : null}

                    {isScheduled ? (
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50/50 p-4">
                        <div>
                          <p className="text-sm font-semibold">Campanha agendada</p>
                          <p className="text-xs text-muted-foreground">
                            {selected.scheduled_for ? new Date(selected.scheduled_for).toLocaleString("pt-BR", { timeZone: selected.schedule_timezone ?? "UTC" }) : "Data não disponível"}
                            {" · "}{selected.schedule_timezone ?? "Fuso não informado"}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">A data não dispara a campanha. Execução permanece desabilitada.</p>
                        </div>
                        {isAdmin ? (
                          <Button variant="outline" disabled={busy} onClick={() => void perform(
                            () => api.removeRetentionCampaignSchedule(selected.id),
                            "Agendamento removido. A proposta voltou para aprovada."
                          )}>
                            Remover agendamento
                          </Button>
                        ) : null}
                      </div>
                    ) : null}

                    {selected.status === "approved" ? (
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                        <span className="flex items-center gap-2">
                          <CheckCircle2 className="h-4 w-4 shrink-0" />
                          Aprovada por {selected.approved_by ?? "usuário autorizado"}.
                        </span>
                        <Link
                          href={`/disparos?proposal=${encodeURIComponent(selected.id)}`}
                          className="rounded-md border border-emerald-300 bg-white px-3 py-2 text-xs font-semibold text-emerald-900 hover:bg-emerald-100"
                        >
                          Preparar execução no motor de disparos
                        </Link>
                        <p className="basis-full text-xs">
                          A proposta já está aprovada. O motor reutiliza essa aprovação,
                          verifica autorização individual e mantém envios reais bloqueados por padrão.
                        </p>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base"><History className="h-4 w-4" /> Histórico de auditoria</CardTitle>
                    <CardDescription>Eventos imutáveis de edição, revisão, atestado e aprovação.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {auditQuery.isLoading ? <p className="text-sm text-muted-foreground">Carregando histórico…</p> :
                      auditQuery.isError ? <p className="text-sm text-muted-foreground">Histórico indisponível para seu perfil.</p> :
                      auditEvents.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum evento registrado ainda.</p> :
                      <ol className="space-y-3">
                        {auditEvents.map((event) => (
                          <li key={event.id} className="flex gap-3 border-l-2 border-muted pl-3">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium">{event.event_type.replaceAll(".", " ")}</p>
                              <p className="text-xs text-muted-foreground">
                                Revisão {event.revision} · {new Date(event.created_at).toLocaleString("pt-BR")} · ator {event.actor_user_id ?? "indisponível"}
                              </p>
                              {typeof event.details.note === "string" ? (
                                <p className="mt-1 text-xs text-muted-foreground">{event.details.note}</p>
                              ) : null}
                            </div>
                          </li>
                        ))}
                      </ol>
                    }
                  </CardContent>
                </Card>
              </div>
            ) : null}
          </div>
        )}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cronograma de campanhas</CardTitle>
            <CardDescription>Agendamentos persistidos da instituição. A chegada da data não inicia a execução.</CardDescription>
          </CardHeader>
          <CardContent>
            {scheduleQuery.isLoading ? <p className="text-sm text-muted-foreground">Carregando cronograma…</p> :
              scheduleQuery.isError ? <p className="text-sm text-muted-foreground">Cronograma indisponível para seu perfil.</p> :
              (scheduleQuery.data?.schedules.length ?? 0) === 0 ? <p className="text-sm text-muted-foreground">Nenhuma campanha agendada.</p> :
              <ul className="divide-y">
                {scheduleQuery.data?.schedules.map((item) => (
                  <li key={item.proposal_id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <div>
                      <p className="text-sm font-medium">{item.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {item.scheduled_for ? new Date(item.scheduled_for).toLocaleString("pt-BR", { timeZone: item.schedule_timezone ?? "UTC" }) : "Data indisponível"}
                        {" · "}{item.schedule_timezone ?? "Fuso não informado"}
                      </p>
                    </div>
                    <span className="rounded-full bg-muted px-2 py-1 text-xs font-medium">Agendada · sem execução</span>
                  </li>
                ))}
              </ul>
            }
          </CardContent>
        </Card>
        <div className="flex items-start gap-2 rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          Aprovação não comprova legalidade por si só. A instituição revisa a base de contato.
          A execução é preparada no motor compartilhado de disparos, sem envio nesta tela.
        </div>
      </main>
      <RecordDrawer record={previewProposal?{
          kind:"campaign",id:previewProposal.id,title:previewProposal.title,
          caption:"Proposta de campanha",subtitle:previewProposal.objective,
        }:null}
        onClose={()=>setPreviewId(null)}>
        {previewProposal && <RecordSections key={previewProposal.id} sections={[
          {id:"properties",label:"Propriedades",content:<div className="space-y-4">
            <RecordProperties compact groups={[{id:"campaign",title:"Dados da proposta",properties:[
              {key:"status",label:"Estado",value:statusLabels[previewProposal.status]||previewProposal.status,type:"status"},
              {key:"objective",label:"Objetivo",value:previewProposal.objective},
              {key:"revision",label:"Revisão",value:previewProposal.revision,type:"number"},
              {key:"audience",label:"Público avaliado",value:previewProposal.audience_total,type:"number"},
              {key:"channels",label:"Canais recomendados",value:previewProposal.recommended_channels.join(", ")||null},
              {key:"created",label:"Criada em",value:previewProposal.created_at,type:"date"},
              {key:"auth",label:"Situação de autorização",value:previewProposal.authorization_status,type:"status"},
            ]}]}/>
            <RecordRelations relations={previewProposal.source_group_ids.map(id=>({
              id,label:"Grupo de origem",value:id,
              href:canSeeGroups?"/alunos/grupos/"+encodeURIComponent(id):undefined,
              type:"student_group",
            }))}/>
          </div>},
          {id:"activity",label:"Atividade",content:<RecordActivity events={[
            {id:"created:"+previewProposal.id,kind:"status",at:previewProposal.created_at,
              title:"Proposta registrada",origin:"Campanhas",status:"Criada"},
            ...(previewProposal.reviewed_at?[{id:"review:"+previewProposal.id,kind:"status" as const,
              at:previewProposal.reviewed_at,title:"Revisão registrada",origin:"Campanhas",
              status:previewProposal.status}]:[]),
            ...(previewProposal.approved_at?[{id:"approve:"+previewProposal.id,kind:"status" as const,
              at:previewProposal.approved_at,title:"Aprovação registrada",origin:"Campanhas",
              status:"Aprovada"}]:[]),
          ]}/>},
        ]}/>}
      </RecordDrawer>
    </>
  );
}

export default function CampaignProposalsPage() {
  return <Suspense fallback={<main className="mira-page p-6 text-xs" role="status">
    Carregando campanhas autorizadas…
  </main>}>
    <CampaignProposalsContent />
  </Suspense>;
}
