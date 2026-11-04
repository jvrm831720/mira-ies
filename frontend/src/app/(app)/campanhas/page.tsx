"use client";

import { useEffect, useMemo, useState } from "react";
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
} from "lucide-react";
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
};

const channelLabels: Record<string, string> = {
  email: "E-mail",
  whatsapp: "WhatsApp",
  sms: "SMS",
  operacao_interna: "Operação interna",
};

function CampaignProposalsContent() {
  const queryClient = useQueryClient();
  const proposalsQuery = useQuery({
    queryKey: ["retention-campaign-proposals"],
    queryFn: () => api.retentionCampaignProposals(),
  });
  const meQuery = useQuery({ queryKey: ["org-me"], queryFn: () => api.me() });
  const proposals = proposalsQuery.data?.proposals ?? [];
  const [selectedId, setSelectedId] = useState("");
  const selected = proposals.find((item) => item.id === selectedId) ?? null;
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
  const canApprove = Boolean(
    inReview && isAdmin && !isCreator && selected?.authorization_status === "institution_attested"
  );

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["retention-campaign-proposals"] });
    await queryClient.invalidateQueries({ queryKey: ["retention-campaign-proposal-audit", selectedId] });
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
            Execução e agendamento desabilitados
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
          <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
            <section className="space-y-3" aria-label="Lista de propostas">
              {proposals.map((proposal) => (
                <button
                  key={proposal.id}
                  type="button"
                  onClick={() => setSelectedId(proposal.id)}
                  className={`w-full rounded-xl border p-4 text-left transition-colors ${selectedId === proposal.id ? "border-blue-500 bg-blue-50/60" : "border-border bg-card hover:bg-muted/40"}`}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-muted-foreground">REV. {proposal.revision}</span>
                    <span className="rounded-full bg-muted px-2 py-1 text-[11px] font-medium">{statusLabels[proposal.status]}</span>
                  </div>
                  <p className="font-semibold">{proposal.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{proposal.objective}</p>
                  <p className="mt-3 text-xs text-muted-foreground">
                    {proposal.audience_total.toLocaleString("pt-BR")} alunos · {proposal.source_group_ids.length} grupos
                  </p>
                </button>
              ))}
            </section>

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
                          "Proposta aprovada. Execução continua desabilitada."
                        )}>
                          <CheckCircle2 className="mr-2 h-4 w-4" /> Aprovar proposta
                        </Button>
                      </div>
                    ) : null}

                    {selected.status === "approved" ? (
                      <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                        <CheckCircle2 className="h-4 w-4" />
                        Aprovada por {selected.approved_by ?? "usuário autorizado"}. Execução permanece desabilitada.
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
        <div className="flex items-start gap-2 rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          Aprovação não comprova legalidade por si só. A instituição é responsável pela revisão da autorização e da documentação. Esta tela não executa campanhas.
        </div>
      </main>
    </>
  );
}

export default function CampaignProposalsPage() {
  return <CampaignProposalsContent />;
}
