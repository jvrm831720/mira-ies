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
    return "border-[#CBF7E1] bg-[#E0FCED] text-[#007D53]";
  if (status === "rejected" || status === "cancelled")
    return "border-[#FEE7E7] bg-[#FFF2F2] text-[#772322]";
  if (status === "in_review")
    return "border-[#D6E5FF] bg-[#E5EEFF] text-[#006699]";
  return "border-[#E6E7EA] bg-[#F8F9FA] text-[#505967]";
}
