/** Wave 0.4 — read-only projections of existing operational contracts.
 * No connection, run or quality score is inferred from a catalog entry.
 */
export type ConnectionEvidence = {
  configured: boolean;
  enabled?: boolean;
  status?: string | null;
  last_sync_status?: string | null;
  last_sync_at?: string | null;
  last_error?: string | null;
};

export type DisplayState = {
  key: "unconfigured" | "disabled" | "configured" | "authenticated" | "syncing" | "synced" | "error" | "disconnected" | "unknown";
  label: string;
  tone: "neutral" | "blue" | "green" | "red" | "amber";
};

export function connectionState(connection: ConnectionEvidence | null | undefined): DisplayState {
  if (!connection || !connection.configured) return { key: "unconfigured", label: "Não configurado", tone: "neutral" };
  if (connection.enabled === false) return { key: "disabled", label: "Desativado", tone: "neutral" };
  const sync = (connection.last_sync_status || "").trim().toLowerCase();
  const status = (connection.status || "").trim().toLowerCase();
  if (["failed", "error", "erro", "falhou"].includes(sync) || ["error", "failed"].includes(status))
    return { key: "error", label: "Erro", tone: "red" };
  if (["running", "processing", "retrying", "queued", "syncing"].includes(sync))
    return { key: "syncing", label: "Sincronizando", tone: "blue" };
  if (["success", "succeeded", "completed", "done", "synced"].includes(sync) && connection.last_sync_at)
    return { key: "synced", label: "Sincronizado", tone: "green" };
  if (["authenticated", "connected"].includes(status))
    return { key: "authenticated", label: status === "connected" ? "Conectado" : "Autenticado", tone: "green" };
  if (["disconnected", "revoked"].includes(status))
    return { key: "disconnected", label: "Desconectado", tone: "amber" };
  return { key: "configured", label: "Configurado", tone: "blue" };
}

export function runState(status: string | null | undefined): DisplayState {
  const value = (status || "").trim().toLowerCase();
  if (["completed", "success", "succeeded", "processed", "scored", "concluida", "concluída"].includes(value))
    return { key: "synced", label: "Concluído", tone: "green" };
  if (["failed", "error", "erro", "falha"].includes(value))
    return { key: "error", label: "Falhou", tone: "red" };
  if (["queued", "pending", "received", "scheduled"].includes(value))
    return { key: "configured", label: "Preparado", tone: "amber" };
  if (["running", "processing", "retrying"].includes(value))
    return { key: "syncing", label: "Em execução", tone: "blue" };
  if (["cancelled", "canceled"].includes(value))
    return { key: "disabled", label: "Cancelado", tone: "neutral" };
  return { key: "unknown", label: status ? "Estado: " + status : "Desconhecido", tone: "neutral" };
}

export type ImportEvidence = {
  id: string;
  filename: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  error_message?: string | null;
};
export type DataIssue = {
  id: string;
  source: string;
  title: string;
  detail: string;
  kind: "failed" | "partial";
};

export function importIssues(rows: ImportEvidence[]): DataIssue[] {
  return rows.flatMap(row => {
    const result: DataIssue[] = [];
    const state = runState(row.status);
    if (state.key === "error") {
      result.push({ id: row.id + ":error", source: row.filename,
        title: "Importação com falha", detail: row.error_message || "Verifique o histórico desta importação.", kind: "failed" });
    } else if (state.key === "synced" && row.total_rows > row.processed_rows && row.processed_rows >= 0) {
      result.push({ id: row.id + ":partial", source: row.filename,
        title: "Processamento parcial", detail: String(row.processed_rows) + " de " + String(row.total_rows) + " linhas processadas. Inspecione o lote para saber o motivo.", kind: "partial" });
    }
    return result;
  });
}

export function categoryLabel(value: string | null | undefined): string {
  const raw = (value || "").trim().toLowerCase();
  const labels: Record<string, string> = {
    academic: "Sistemas acadêmicos", academics: "Sistemas acadêmicos", education: "Sistemas acadêmicos",
    erp: "Financeiro e ERP", finance: "Financeiro e ERP", financial: "Financeiro e ERP",
    lms: "Sistemas acadêmicos", crm: "CRM", communication: "Comunicação",
    messaging: "Comunicação", document: "Documentos", documents: "Documentos",
    analytics: "Análise de dados", support: "Atendimento", productivity: "Produtividade",
  };
  return labels[raw] || (value?.trim() || "Outros sistemas");
}
