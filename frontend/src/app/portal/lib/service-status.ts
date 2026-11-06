/** Human-readable student-facing labels for the API's finite request-state contract. */
const LABELS: Record<string, string> = {
  submitted: "Solicitada",
  in_review: "Em análise",
  approved: "Aprovada",
  rejected: "Rejeitada",
  completed: "Concluída",
  cancelled: "Cancelada",
};

export function serviceStatusLabel(status: string): string {
  return LABELS[status] ?? status.replaceAll("_", " ");
}

export function serviceStatusTone(status: string): string {
  if (status === "approved" || status === "completed")
    return "border-[var(--color-green-tint-border)] bg-[var(--color-green-tint)] text-[var(--color-green)]";
  if (status === "rejected" || status === "cancelled")
    return "border-[var(--color-red-tint-border)] bg-[var(--color-legacy-fff2f2)] text-[var(--color-red)]";
  if (status === "in_review")
    return "border-[var(--color-blue-tint-border)] bg-[var(--color-blue-tint)] text-[var(--color-blue-ink)]";
  return "border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-slate-600)]";
}
