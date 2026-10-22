export type AuthResponse = {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  user?: { display_name?: string; email?: string; tenant_name?: string };
};

export type AuthActionResponse = { message: string };

export type RiskSummary = {
  total_scored?: number;
  total_students?: number;
  summary: { baixo: number; medio: number; critico: number; sem_score: number };
};

export type CriticalStudent = {
  id: string;
  nome: string;
  matricula?: string;
  curso?: string;
  risk_level?: string;
  risk_score?: number;
};

export type CriticalResponse = { students: CriticalStudent[] };

export type StudentsResponse = {
  students: Array<{
    id: string;
    nome: string;
    matricula?: string;
    curso?: string;
    risk_level?: string;
    risk_score?: number;
  }>;
};

export type StudentRisk = {
  id: string;
  nome?: string | null;
  matricula?: string | null;
  curso?: string | null;
  telefone?: string | null;
  email?: string | null;
  communication_opt_out?: boolean;
  risk_score?: number | null;
  risk_level?: string | null;
  shap_summary?: string | null;
  shap_top_factors?: {
    summary?: string;
    top_3?: Array<{ feature?: string; label?: string }>;
    recommended_actions?: string[];
  } | null;
  recommended_actions?: string[] | null;
};

export type CommunicationPreferenceResponse = { opt_out: boolean };

export type UploadResponse = {
  message?: string;
  students_imported?: number;
  batch?: { id?: string };
  scoring?: {
    scored?: number;
    summary?: { critico?: number; medio?: number; baixo?: number };
  } | null;
};

export type ModelInfo = {
  status?: "ready" | "error";
  version?: string | null;
  auc?: number | null;
  model_scope?: string;
  disclaimer?: string;
  training_data?: string;
  hybrid?: string;
  shap_on_batch_default?: boolean;
  message?: string;
};

export type AgentsStatus = {
  dry_run_default: boolean;
  anti_spam: {
    min_hours_between_contact: number;
    max_contacts_per_week: number;
  };
  providers: Record<"whatsapp" | "email" | "sms", string>;
  queue?: {
    name?: string;
    dead_letter_name?: string;
    max_attempts?: number;
    retry_backoff_seconds?: number;
  };
};

export type RiskLevel = "baixo" | "medio" | "critico";

export type RetentionRunRequest = {
  dry_run?: boolean;
  risk_levels?: RiskLevel[];
  limit?: number;
  channels?: Array<"whatsapp" | "email" | "sms">;
  prefer_whatsapp_medio?: boolean;
  batch_id?: string;
  student_ids?: string[];
  campaign_name?: string;
  campaign_id?: string;
};

export type RetentionRunResult = {
  message?: string;
  campaign_id?: string | null;
  students_evaluated?: number;
  totals?: Partial<Record<"sent" | "dry_run" | "skipped" | "failed" | "unknown", number>>;
  by_channel?: Record<string, Partial<Record<string, number>>>;
};

export type LogsResponse = {
  logs: Array<{
    id: string;
    student_id?: string;
    matricula?: string | null;
    channel?: string | null;
    risk_level?: string | null;
    status: string;
    delivery_status?: string | null;
    created_at?: string | null;
    campaign_id?: string | null;
    message_preview?: string | null;
    skip_reason?: string | null;
    error?: string | null;
  }>;
  count?: number;
};

export type InterventionLog = LogsResponse["logs"][number];

export type PreviewMessage = Record<string, unknown>;

export type MemberRole = "admin" | "coordinator" | "operator" | "viewer";

export type OrgMember = {
  id: string;
  email: string;
  display_name?: string | null;
  role: MemberRole;
  status: string;
  phone?: string | null;
  created_at?: string | null;
};

export type OrgInvite = {
  id: string;
  email: string;
  role: MemberRole;
  status: string;
  created_at?: string | null;
  expires_at?: string | null;
};

export type MembersResponse = {
  organization_name?: string;
  members: OrgMember[];
};

export type InvitesResponse = { invites: OrgInvite[] };

export type InviteMemberRequest = { email: string; role: MemberRole };

export type InviteMemberResponse = {
  message?: string;
  invite_url?: string;
  invite?: OrgInvite;
};

export type AcceptInviteRequest = {
  token: string;
  password: string;
  display_name?: string;
  phone?: string;
};

export type BillingInvoice = {
  id: string;
  date: string;
  amount_brl: number;
  label?: string;
  download_url?: string | null;
};

export type BillingSummary = {
  plan_name: string;
  plan_status: "active" | "past_due" | "trialing";
  plan_price_brl: number;
  billing_cycle: "monthly" | "yearly";
  renews_at: string;
  next_invoice_brl: number;
  period_spend_brl: number;
  period_messages: number;
  payment_link?: string | null;
  credits: { whatsapp: number; email: number; sms: number };
  used_period: { whatsapp: number; email: number; sms: number };
  invoices: BillingInvoice[];
};

export type PurchaseCreditsRequest = {
  channel: "whatsapp" | "email" | "sms";
  pack_id: string;
  credits: number;
};

export type PurchaseCreditsResponse = {
  channel: string;
  added: number;
  balance: number;
};
