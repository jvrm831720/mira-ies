export type RiskLevel = "baixo" | "medio" | "critico";

export type MemberRole = "admin" | "coordinator" | "operator" | "viewer";

export interface AuthUser {
  display_name: string;
  email: string;
  tenant_name: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer" | string;
  expires_in: number;
  user: AuthUser;
}

export interface AuthActionResponse {
  message?: string;
}

export interface OrgMember {
  id: string;
  email: string;
  display_name?: string | null;
  role: MemberRole;
  status: "active" | "invited" | "disabled" | string;
  phone?: string | null;
  created_at?: string | null;
}

export interface OrgInvite {
  id: string;
  email: string;
  role: MemberRole;
  status: "pending" | "accepted" | "expired" | "revoked" | string;
  created_at?: string | null;
  expires_at?: string | null;
  invite_url?: string | null;
}

export interface MembersResponse {
  members: OrgMember[];
  organization_name?: string;
}

export interface InvitesResponse {
  invites: OrgInvite[];
}

export interface InviteMemberRequest {
  email: string;
  role: MemberRole;
}

export interface InviteMemberResponse {
  message?: string;
  invite?: OrgInvite;
  invite_url?: string;
}

export interface AcceptInviteRequest {
  token: string;
  password: string;
  phone: string;
  display_name?: string;
}

export interface RiskSummary {
  summary: {
    baixo: number;
    medio: number;
    critico: number;
    sem_score?: number;
  };
  total_scored?: number;
  total_students?: number;
  batch_id?: string | null;
  tenant_id?: string;
}

export interface StudentRisk {
  id: string;
  matricula: string;
  nome: string;
  curso?: string | null;
  turma?: string | null;
  semestre?: number | null;
  risk_score?: number | null;
  risk_level?: RiskLevel | null;
  shap_summary?: string | null;
  shap_top_factors?: {
    top_3?: Array<{ feature?: string; label?: string; value?: number }>;
    summary?: string;
    recommended_actions?: string[];
    confidence?: string;
    model_scope?: string;
  } | null;
  recommended_actions?: string[] | null;
  telefone?: string | null;
  email?: string | null;
  communication_opt_out?: boolean;
  dias_atraso_boleto?: number | null;
  dias_sem_login?: number | null;
  presenca_percentual?: number | null;
  nota_media?: number | null;
}

export interface StudentsResponse {
  count: number;
  students: StudentRisk[];
}

export interface CommunicationPreferenceResponse {
  student_id: string;
  communication_opt_out: boolean;
  communication_opted_out_at?: string | null;
}

export interface CriticalResponse {
  count: number;
  tenant_id?: string;
  students: StudentRisk[];
}

export interface UploadResponse {
  message: string;
  batch?: {
    id: string;
    original_filename?: string;
    status?: string;
    processed_rows?: number;
  };
  students_imported?: number;
  quality?: Record<string, unknown>;
  scoring?: {
    scored?: number;
    summary?: Record<string, number>;
    error?: string;
  };
  preview?: StudentRisk[];
}

export interface RetentionRunRequest {
  batch_id?: string | null;
  campaign_id?: string | null;
  risk_levels?: RiskLevel[];
  limit?: number;
  dry_run?: boolean | null;
  channels?: Array<"whatsapp" | "email" | "sms"> | null;
  prefer_whatsapp_medio?: boolean;
}

export interface RetentionRunResult {
  message?: string;
  dry_run?: boolean;
  totals?: Record<string, number>;
  by_channel?: Record<string, Record<string, number>>;
  results?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface InterventionLog {
  id: string;
  student_id?: string | null;
  matricula?: string | null;
  channel?: string | null;
  risk_level?: string | null;
  status: string;
  skip_reason?: string | null;
  error?: string | null;
  provider?: string | null;
  external_id?: string | null;
  correlation_id?: string | null;
  idempotency_key?: string | null;
  job_id?: string | null;
  campaign_id?: string | null;
  delivery_status?: string | null;
  delivery_event_id?: string | null;
  delivery_updated_at?: string | null;
  message_preview?: string | null;
  created_at?: string | null;
}

export interface LogsResponse {
  count: number;
  logs: InterventionLog[];
}

export interface AgentsStatus {
  dry_run_default: boolean;
  anti_spam: {
    min_hours_between_contact: number;
    max_contacts_per_week: number;
  };
  providers: {
    whatsapp: string;
    email: string;
    sms: string;
  };
  queue?: {
    name: string;
    dead_letter_name: string;
    max_attempts: number;
    retry_backoff_seconds: number;
  };
}

export interface ModelInfo {
  status: string;
  version?: string;
  auc?: number;
  model_scope?: string;
  training_data?: string;
  hybrid?: string;
  disclaimer?: string;
}

export interface PreviewMessage {
  student_id?: string;
  matricula?: string;
  channel?: string;
  message?: string;
  risk_level?: string;
  [key: string]: unknown;
}
