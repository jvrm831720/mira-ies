import type { WorkResultKind } from "@/types/work";

export function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export const STATUS_LABEL: Record<string, string> = {
  open: "Aberta",
  in_progress: "Em andamento",
  completed: "Concluída",
  cancelled: "Cancelada",
};

export const TYPE_LABEL: Record<string, string> = {
  follow_up: "Follow-up",
  contact: "Contato",
  review: "Revisão",
  other: "Outro",
};

export const PRIORITY_LABEL: Record<string, string> = {
  low: "Baixa",
  normal: "Normal",
  high: "Alta",
  urgent: "Urgente",
};

export const ORIGIN_LABEL: Record<string, string> = {
  manual: "Equipe",
  campaign: "Campanha",
};

export const EVENT_LABEL: Record<string, string> = {
  created: "Criação",
  assignee_changed: "Responsável",
  due_changed: "Prazo",
  status_changed: "Status",
  completed: "Conclusão",
  cancelled: "Cancelamento",
  result_recorded: "Resultado operacional",
  priority_changed: "Prioridade",
  details_changed: "Detalhes",
  relations_changed: "Vínculos",
};

export const RESULT_KIND_LABEL: Record<WorkResultKind, string> = {
  done: "Concluída",
  unreachable: "Não conseguiu contato",
  deferred: "Adiada",
  referred: "Encaminhada",
};

export const CHANNEL_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  email: "E-mail",
  sms: "SMS",
};

