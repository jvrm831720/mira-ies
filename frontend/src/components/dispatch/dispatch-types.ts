import type { DispatchCampaign } from "@/lib/dispatch-api";

export type DispatchSection = "overview" | "campaigns" | "monitor" | "results";
export type DispatchPurpose = DispatchCampaign["purpose"];
export type DispatchChannel = DispatchCampaign["channel"];
export type DispatchStatus = DispatchCampaign["status"];

export type CampaignBuilderState = {
  name: string;
  purpose: DispatchPurpose;
  mode: "targeted" | "bulk";
  sourceKey: string;
  channel: DispatchChannel;
  templateId: string;
  perMinute: number;
};

export type CampaignBuilderContext = {
  templates: DispatchTemplate[];
  sources: DispatchSource[];
  profile?: string | null;
};

export type DispatchListCounts = {
  rows: number;
  drafts: number;
  approved: number;
  scheduled: number;
  running: number;
  paused: number;
  completed: number;
  cancelled: number;
  withProblems: number;
};

export const PURPOSE_LABEL: Record<DispatchPurpose, string> = {
  retention: "Permanência",
  academic: "Acadêmico",
  service: "Atendimento",
  collections: "Cobrança",
};
export const CHANNEL_LABEL: Record<DispatchChannel, string> = {
  email: "E-mail",
  sms: "SMS",
  whatsapp: "WhatsApp",
};
export const CAMPAIGN_STATUS_LABEL: Record<DispatchStatus, string> = {
  draft: "Rascunho",
  approved: "Aprovada",
  scheduled: "Agendada",
  running: "Em execução",
  paused: "Pausada",
  completed: "Concluída",
  cancelled: "Cancelada",
};
export const ITEM_STATUS_LABEL: Record<string,string> = {
  queued: "Na fila",
  retry_wait: "Aguardando nova tentativa",
  leased: "Reservado pelo worker",
  sending: "Em processamento",
  sent: "Aceito pelo provedor",
  delivered: "Entrega confirmada",
  read: "Leitura confirmada",
  replied: "Resposta registrada",
  simulated: "Simulado",
  blocked: "Bloqueado",
  failed: "Falha registrada",
  unknown: "Resultado desconhecido",
  suppressed: "Suprimido",
};
export const ITEM_TERMINAL = new Set(["blocked", "failed", "unknown", "suppressed"]);
export const VALID_SECTIONS: DispatchSection[] = ["overview", "campaigns", "monitor", "results"];
