import type { DispatchCampaign, DispatchTemplate, DispatchSource } from "@/lib/dispatch-api";
import type { CampaignBuilderState, DispatchListCounts, DispatchPurpose } from "./dispatch-types";

export const MAX_CAMPAIGN_PREVIEW = 50;
export const MAX_ITEMS_PREVIEW = 100;

export function readableDate(raw: string | null | undefined): string {
  if (!raw) return "Não registrado";
  const dt = new Date(raw);
  return Number.isNaN(dt.getTime()) ? "Não registrado"
    : new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo",
      }).format(dt);
}

export function countCampaignPreview(items: DispatchCampaign[]): DispatchListCounts {
  const statuses = (name: string) => items.filter(item => item.status === name).length;
  return {
    rows: items.length, drafts: statuses("draft"), approved: statuses("approved"),
    scheduled: statuses("scheduled"), running: statuses("running"),
    paused: statuses("paused"), completed: statuses("completed"),
    cancelled: statuses("cancelled"),
    withProblems: items.filter(item => item.problems > 0).length,
  };
}

export function permittedPurposes(profile?: string | null): DispatchPurpose[] {
  if (profile === "institution") return ["retention", "academic", "service"];
  if (profile && ["collection", "debt_collection", "billing", "cobranca"].includes(profile))
    return ["collections", "service"];
  return []; // Unknown tenant profile is not a licence to send.
}

export function validChannel(purpose: DispatchPurpose, channel: string): boolean {
  // The backend explicitly refuses collections+WhatsApp.
  return ["email", "sms"].includes(channel);
  // The current delivery service only sends email/SMS; no live WhatsApp adapter.
}

export function sourceKey(source: DispatchSource): string {
  return source.kind + ":" + (source.reference || "") + ":" + (source.toolkit || "");
}
export function eligibleSources(sources: DispatchSource[]): DispatchSource[] {
  return sources.filter(s => s.connected && s.can_bind &&
    // A Composio source without a tool is not yet an executable audience.
    (s.kind !== "composio" || (s.tools || []).length > 0));
}
export function matchingTemplates(
  templates: DispatchTemplate[], purpose: DispatchPurpose, channel: string,
): DispatchTemplate[] {
  return templates.filter(t => t.status === "approved" && t.purpose === purpose
    && t.channel === channel && validChannel(purpose, channel));
}
export function validateCampaignDraft(
  draft: CampaignBuilderState, sources: DispatchSource[], templates: DispatchTemplate[],
  profile?: string | null,
): string[] {
  const failures: string[] = [];
  if (!permittedPurposes(profile).includes(draft.purpose)) failures.push("Finalidade indisponível para este workspace.");
  if (draft.name.trim().length < 3 || draft.name.trim().length > 160) failures.push("O nome deve ter entre 3 e 160 caracteres.");
  if (!validChannel(draft.purpose, draft.channel)) failures.push("Canal bloqueado para essa finalidade.");
  if (!Number.isInteger(draft.perMinute) || draft.perMinute < 1 || draft.perMinute > 120)
    failures.push("O limite por minuto deve ficar entre 1 e 120.");
  const source = eligibleSources(sources).find(s => sourceKey(s) === draft.sourceKey);
  if (!source) failures.push("Selecione uma origem conectada e autorizada.");
  const template = matchingTemplates(templates, draft.purpose, draft.channel).find(t => t.id === draft.templateId);
  if (!template) failures.push("Selecione um modelo aprovado para finalidade e canal.");
  if (template && (template.body.length < 3 || template.body.length > 2000))
    failures.push("O corpo do modelo não é compatível com a criação de campanhas.");
  return failures;
}

export function postSendLabel(state: string): string {
  switch (state) {
    case "sent": return "Aceito pelo provedor";
    case "delivered": return "Entregue (confirmado)";
    case "read": return "Lido (confirmado)";
    case "replied": return "Respondido";
    case "unknown": return "Resultado desconhecido";
    default: return state;
  }
}

export function countItemStates(items: Array<{ status: string }>): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});
}
