/** Tipos da API de inteligência de sinais (GET /api/v1/signals/*). */

export type StudentSignalEvaluation = {
  signal_id: string;
  name?: string;
  category?: string;
  active?: boolean;
  status?: "TRUE" | "FALSE" | "INDETERMINATE" | string;
  insufficient_data?: boolean;
  evidence?: Record<string, unknown>;
  reliability?: string;
  signal_version?: string;
  evaluated_at?: string;
  limitations?: string[];
  description?: string;
};

export type SignalsEvaluateResponse = {
  student_id: string;
  tenant_id: string;
  evaluated_at: string;
  active_signal_ids: string[];
  signals: StudentSignalEvaluation[];
};

export type SignalsCatalogResponse = {
  count: number;
  catalog_version: string;
  signals: Array<{
    id: string;
    name: string;
    category: string;
    description: string;
    reliability_class: string;
    activation_rule: string;
    data_source: string;
    version: string;
    limitations: string[];
  }>;
  tenant_id: string;
};
