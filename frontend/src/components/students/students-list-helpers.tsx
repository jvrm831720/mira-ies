"use client";

export type StudentTab = "todos" | "risco" | "sem_classificacao" | "dados_insuficientes" | "acompanhamento";
export type StudentSort = "risk_desc" | "risk_asc" | "name_asc";

export const KNOWN_GROUP_IDS = new Set([
  "risk_critical",
  "risk_medium",
  "financial_delay",
  "days_without_login_elevated",
  "risk_increase",
  "multiple_active_signals",
  "missing_score",
]);

export function initials(name?: string | null) {
  if (!name?.trim()) return "—";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toLocaleUpperCase("pt-BR");
}

export function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function followUpLabel(status?: string) {
  if (!status) return "Sem registro";
  const normalized = status.toLowerCase();
  if (["planned", "pending", "queued"].includes(normalized)) return "Aguardando ação";
  if (["sent", "delivered", "read", "replied", "in_progress"].includes(normalized))
    return "Em acompanhamento";
  if (["failed", "error", "skipped"].includes(normalized)) return "Requer revisão";
  if (["completed", "done", "resolved"].includes(normalized)) return "Concluído";
  return status.replaceAll("_", " ");
}

export function businessSignalText(raw?: string | null): string | null {
  if (!raw?.trim()) return null;
  const t = raw.trim();
  if (/\/api\/|GET\s+\/|POST\s+\/|SHAP sob demanda|students\/\{?id\}?\/risk/i.test(t)) {
    return null;
  }
  return t;
}

export function primarySignal(student: {
  risk_level?: string | null;
  risk_score?: number | null;
  shap_summary?: string | null;
  shap_top_factors?: {
    summary?: string;
    top_3?: Array<{ feature?: string; label?: string }>;
    recommended_actions?: string[];
  } | null;
}): { signal: string | null; action: string | null; empty: string } {
  if (!student.risk_level || student.risk_score == null) {
    return {
      signal: null,
      action: null,
      empty: "Ainda não há evidências calculadas",
    };
  }
  const fromSummary = businessSignalText(student.shap_summary);
  const fromFactors = student.shap_top_factors?.top_3
    ?.map((f) => businessSignalText(f.label) || businessSignalText(f.feature))
    .filter(Boolean)
    .join(" · ");
  const signal = fromSummary || fromFactors || null;
  const actionRaw = student.shap_top_factors?.recommended_actions?.[0];
  const action = businessSignalText(actionRaw);
  return {
    signal,
    action,
    empty: "Explicação detalhada indisponível",
  };
}
