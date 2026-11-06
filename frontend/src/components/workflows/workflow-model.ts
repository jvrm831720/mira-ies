import type { RetentionCampaignProposal } from "@/types/api";
import type { DispatchCampaign } from "@/lib/dispatch-api";

/**
 * Presentation-only projections. These are NOT workflow definitions, nodes stored
 * by the backend, scheduled executions, or evidence of message delivery.
 */
export type WorkflowRecord =
  | { kind: "proposal"; id: string; title: string; status: string; updatedAt: string; source: RetentionCampaignProposal }
  | { kind: "dispatch"; id: string; title: string; status: string; updatedAt: string; source: DispatchCampaign };

export type BlockState = "verified" | "pending" | "attention" | "unavailable";
export type WorkflowBlock = {
  id: string;
  title: string;
  description: string;
  state: BlockState;
  source: string;
  requiredPermission: string;
  details: Array<{ label: string; value: string }>;
};

export const PROPOSAL_STATUS: Record<string, string> = {
  draft: "Rascunho", in_review: "Em revisão", changes_requested: "Ajustes solicitados",
  approved: "Aprovada", scheduled: "Agendada (metadados)", running: "Em andamento",
  paused: "Pausada", completed: "Concluída", cancelled: "Cancelada", failed: "Falhou",
};
export const DISPATCH_STATUS: Record<string, string> = {
  draft: "Rascunho", approved: "Aprovada", scheduled: "Agendada",
  running: "Executando", paused: "Pausada", completed: "Concluída", cancelled: "Cancelada",
};

export function statusLabel(status: string, kind: WorkflowRecord["kind"]): string {
  return (kind === "proposal" ? PROPOSAL_STATUS : DISPATCH_STATUS)[status] ?? status;
}

export function workflowRecords(
  proposals: RetentionCampaignProposal[],
  campaigns: DispatchCampaign[],
): WorkflowRecord[] {
  return [
    ...proposals.map((p): WorkflowRecord => ({
      kind: "proposal", id: p.id, title: p.title, status: p.status, updatedAt: p.updated_at, source: p,
    })),
    ...campaigns.map((p): WorkflowRecord => ({
      kind: "dispatch", id: p.id, title: p.name, status: p.status, updatedAt: p.created_at, source: p,
    })),
  ].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

function block(
  id: string, title: string, description: string, state: BlockState,
  requiredPermission: string, source: string,
  details: Array<{ label: string; value: string }> = [],
): WorkflowBlock {
  return { id, title, description, state, requiredPermission, source, details };
}
const show = (value: unknown) => value === null || value === undefined || value === "" ? "Não informado" : String(value);
const count = (value: number) => value.toLocaleString("pt-BR");

export function blocksForWorkflow(record: WorkflowRecord, linkedDispatch: DispatchCampaign[] = []): WorkflowBlock[] {
  if (record.kind === "proposal") {
    const p = record.source;
    const reviewed = Boolean(p.reviewed_at);
    const attested = p.authorization_status === "institution_attested" && Boolean(p.authorization_attested_at);
    const approved = Boolean(p.approved_at);
    const scheduled = Boolean(p.scheduled_for);
    const linked = linkedDispatch.filter(c => c.origin_proposal_id === p.id);
    const hasExecuted = linked.some(c => ["running", "paused", "completed"].includes(c.status));
    return [
      block("audience", "Público identificado", "Grupos registrados na proposta", "verified", "campaigns.view",
        "Snapshot da proposta", [
          { label: "Grupos", value: count(p.source_group_ids.length) },
          { label: "Público", value: count(p.audience_total) },
          { label: "Catálogo", value: show(p.source_catalog_version) },
        ]),
      block("eligibility", "Verificar elegibilidade", "Estimativas registradas, não confirmação de contato",
        "verified", "campaigns.view", "Snapshot da proposta", [
          { label: "Elegíveis estimados", value: count(p.outreach_eligible_count) },
          { label: "Bloqueados", value: count(p.blocked_count) },
          { label: "Ações internas", value: count(p.internal_action_count) },
        ]),
      block("proposal", "Preparar proposta", "Conteúdo versionado e persistido", "verified",
        "campaigns.edit", "Proposta de permanência v" + p.revision, [
          { label: "Revisão", value: "v" + p.revision },
          { label: "Objetivo", value: show(p.objective) },
          { label: "Canais sugeridos", value: p.recommended_channels.join(", ") || "Não informado" },
        ]),
      block("review", "Revisar", "Revisão por responsável institucional",
        p.status === "changes_requested" ? "attention" : reviewed ? "verified" : "pending",
        "campaigns.approve", "Histórico de revisão", [
          { label: "Revisor", value: show(p.reviewed_by) },
          { label: "Revisado em", value: show(p.reviewed_at) },
        ]),
      block("authorization", "Atestar autorização", "A declaração precisa existir antes da aprovação",
        attested ? "verified" : "pending", "campaigns.approve", "Declaração institucional", [
          { label: "Autorização", value: show(p.authorization_status) },
          { label: "Referência", value: show(p.authorization_reference) },
        ]),
      block("approval", "Aprovar", "Exige responsável habilitado e segregação de funções",
        approved ? "verified" : "pending", "campaigns.approve", "Aprovação da proposta", [
          { label: "Aprovador", value: show(p.approved_by) },
          { label: "Aprovada em", value: show(p.approved_at) },
        ]),
      block("schedule", "Agendamento", "Agendamento de proposta não dispara mensagens",
        scheduled ? "verified" : "pending", "campaigns.execute", "Metadados de agenda", [
          { label: "Horário", value: show(p.scheduled_for) },
          { label: "Fuso", value: show(p.schedule_timezone) },
          { label: "Execução automática", value: "Desabilitada neste contrato" },
        ]),
      block("handoff", "Encaminhar execução", "Somente quando existir disparo vinculado, em serviço separado",
        linked.length ? "verified" : "unavailable", "campaigns.execute", "Dispatch (serviço externo à proposta)", [
          { label: "Campanhas vinculadas", value: count(linked.length) },
          { label: "IDs", value: linked.map(c => c.id).join(", ") || "Nenhuma evidência de encaminhamento" },
        ]),
      block("outcome", "Acompanhar resultados", "Não inferir envio ou conclusão apenas por aprovação",
        hasExecuted ? "verified" : "unavailable", "campaigns.view", "Dispatch vinculado", [
          { label: "Disparos em execução ou concluídos", value: count(linked.filter(c => ["running", "paused", "completed"].includes(c.status)).length) },
          { label: "Itens aceitos pelo dispatch", value: count(linked.reduce((total, c) => total + c.accepted, 0)) },
          { label: "Itens com problemas", value: count(linked.reduce((total, c) => total + c.problems, 0)) },
        ]),
    ];
  }
  const d = record.source;
  const approved = Boolean(d.approved_at) || ["approved", "scheduled", "running", "paused", "completed"].includes(d.status);
  const started = ["running", "paused", "completed"].includes(d.status);
  return [
    block("created", "Campanha registrada", "Configuração existente no disparador", "verified", "campaigns.view", "Dispatch", [
      { label: "Origem", value: show(d.source_kind) }, { label: "Canal", value: d.channel },
      { label: "Modo", value: d.delivery_mode }, { label: "Template", value: d.template_ref },
    ]),
    block("audience", "Público no outbox", "Itens registrados — não equivalem a mensagens enviadas",
      d.total > 0 ? "verified" : "pending", "campaigns.edit", "Dispatch", [
        { label: "Itens totais", value: count(d.total) },
        { label: "Pendentes", value: count(d.pending) },
      ]),
    block("approval", "Aprovação do disparo", "Permissões e evidências controladas pelo serviço",
      approved ? "verified" : "pending", "campaigns.approve", "Dispatch", [
        { label: "Aprovado por", value: show(d.approved_by) },
        { label: "Aprovado em", value: show(d.approved_at) },
      ]),
    block("schedule", "Agendamento", "Data persistida, sem presumir início de execução",
      d.scheduled_for ? "verified" : "pending", "campaigns.execute", "Dispatch", [
        { label: "Agendado para", value: show(d.scheduled_for) },
      ]),
    block("execution", "Operação de envio", "Estado real do disparador; nenhuma ação iniciada por esta tela",
      started ? "verified" : d.status === "cancelled" ? "attention" : "pending",
      "campaigns.execute", "Dispatch", [
        { label: "Estado", value: statusLabel(d.status, "dispatch") },
        { label: "Itens aceitos", value: count(d.accepted) },
        { label: "Problemas", value: count(d.problems) },
      ]),
    block("result", "Resultados observados", "Contagens operacionais, não recuperação financeira",
      d.accepted > 0 || d.problems > 0 || d.status === "completed" ? "verified" : "unavailable",
      "campaigns.view", "Dispatch", [
        { label: "Itens aceitos", value: count(d.accepted) },
        { label: "Falhas / bloqueios / desconhecidos", value: count(d.problems) },
        { label: "Respostas", value: count(d.replied) },
      ]),
  ];
}

export function mayEditProposal(record: WorkflowRecord, canEdit: boolean): boolean {
  return record.kind === "proposal" && canEdit &&
    ["draft", "changes_requested"].includes(record.source.status);
}
