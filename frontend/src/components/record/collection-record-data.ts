import type { CollectionCase, CollectionCaseDetail } from "@/lib/collections-api";
import type { RecordActivityEvent, RecordIdentity, RecordPropertyGroup, RecordRelation } from "./record-types";

export const COLLECTION_TIMELINE_LIMIT = 100;

/** The canonical financial case is read-only and comes from a verified source. */
export function collectionRecordIdentity(id: string, row: CollectionCase | null | undefined): RecordIdentity {
  return {
    kind: "case", id,
    title: row?.external_ref?.trim() || "Caso financeiro",
    caption: "Caso financeiro · Dados da origem",
    subtitle: [row?.source, row?.subject_ref].filter(Boolean).join(" · ") || "Identificação da origem indisponível",
  };
}

const STATUS: Record<string, string> = {
  open: "Aberta", agreement: "Em acordo", paid: "Paga (origem)",
  disputed: "Contestada", cancelled: "Cancelada", unknown: "Não determinada",
};

function amount(value: string | null | undefined): number | null {
  if (value == null || !value.trim()) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function date(value: string | null | undefined): string | null {
  if (!value) return null;
  return Number.isNaN(new Date(value).getTime()) ? null : value;
}

/** Projection is limited to fields returned by GET /collections/cases/{id}. */
export function collectionRecordProperties(row: CollectionCase): RecordPropertyGroup[] {
  return [
    { id: "identification", title: "Identificação e proveniência", properties: [
      { key: "external_ref", label: "Referência", value: row.external_ref },
      { key: "source", label: "Origem", value: row.source },
      { key: "source_version", label: "Versão da origem", value: row.source_version, type: "number" },
      { key: "evidence_ref", label: "Evidência da origem", value: row.evidence_ref },
      { key: "subject_type", label: "Tipo de vínculo", value: row.subject_type === "student" ? "Aluno" : "Externo" },
      { key: "subject_ref", label: "Referência vinculada", value: row.subject_ref },
    ] },
    { id: "financial", title: "Estado financeiro informado", properties: [
      { key: "status", label: "Estado da origem", value: STATUS[row.status] || row.status, type: "status" },
      { key: "balance", label: "Saldo informado", value: amount(row.balance), type: "currency" },
      { key: "verified_at", label: "Verificado em", value: date(row.verified_at), type: "date" },
      { key: "updated_at", label: "Atualizado em", value: date(row.updated_at), type: "date" },
    ] },
  ];
}

export function collectionRecordRelations(row: CollectionCase): RecordRelation[] {
  return [{
    id: "subject", label: row.subject_type === "student" ? "Aluno vinculado" : "Pessoa/entidade vinculada",
    value: row.subject_ref || "Não informado",
    // A source reference is NOT necessarily the MIRA student UUID: never generate a link.
  }];
}

/** Event metadata only. No payment execution, receipts or reconciliation inference. */
export function collectionRecordTimeline(detail: CollectionCaseDetail | null | undefined): {
  events: RecordActivityEvent[]; truncated: boolean;
} {
  if (!detail) return { events: [], truncated: false };
  const source = Array.isArray(detail.payment_events) ? detail.payment_events : [];
  return {
    truncated: Boolean(detail.payment_events_limited) || source.length > COLLECTION_TIMELINE_LIMIT,
    events: source.slice(0, COLLECTION_TIMELINE_LIMIT).map(event => ({
      id: "finance:" + event.id, kind: "finance" as const,
      at: date(event.paid_at),
      title: "Evento financeiro informado pela origem",
      origin: event.source || "Origem não informada",
      status: event.obligation_status || null,
      description: [
        amount(event.amount_paid) == null ? null : "Valor informado: " + new Intl.NumberFormat(
          "pt-BR", { style: "currency", currency: "BRL" },
        ).format(Number(event.amount_paid)),
        amount(event.remaining_balance) == null ? null : "Saldo após evento: " +
          new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
            .format(Number(event.remaining_balance)),
      ].filter(Boolean).join(" · ") || null,
    })),
  };
}

/** No write action in the financial case contract. Editing must remain disabled. */
export const COLLECTION_RECORD_EDITABLE_FIELDS = [] as const;
