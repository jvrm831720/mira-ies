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
  summary: { baixo: number; medio: number; critico: number; sem_score?: number };
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
  id?: string;
  nome?: string;
  matricula?: string;
  curso?: string;
  telefone?: string;
  email?: string;
  risk_level?: string;
  risk_score?: number;
  communication_opt_out?: boolean;
  shap_summary?: string;
  recommended_actions?: string[];
  shap_top_factors?: {
    summary?: string;
    recommended_actions?: string[];
    top_3?: Array<{ label?: string; feature?: string; value?: number }>;
  };
};

export type CommunicationPreferenceResponse = { opt_out: boolean };

export type UploadResponse = {
  message?: string;
  students_imported?: number;
  batch?: { id?: string };
  scoring?: {
    scored?: number;
    summary?: {
      critico?: number;
      medio?: number;
      baixo?: number;
    };
  } | null;
};

export type ModelInfo = {
  status?: string;
  version?: string | null;
  auc?: number | null;
  model_scope?: string;
  training_data?: string;
  hybrid?: string;
  disclaimer?: string;
  shap_on_batch_default?: boolean;
  message?: string;
};

export type AgentsStatus = {
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
    name?: string;
    dead_letter_name?: string;
    max_attempts?: number;
    retry_backoff_seconds?: number;
  };
};

export type RiskLevel = "baixo" | "medio" | "critico";

export type RetentionRunRequest = {
  batch_id?: string;
  campaign_id?: string;
  risk_levels?: RiskLevel[];
  limit?: number;
  dry_run?: boolean | null;
  channels?: Array<"whatsapp" | "email" | "sms">;
  prefer_whatsapp_medio?: boolean;
  student_ids?: string[];
};

export type RetentionRunResult = {
  tenant_id?: string;
  dry_run?: boolean;
  campaign_id?: string;
  students_evaluated?: number;
  by_channel?: Record<string, Record<string, number>>;
  totals?: Partial<Record<"sent" | "dry_run" | "skipped" | "failed" | "unknown", number>>;
  message?: string;
};

export type InterventionLog = {
  id: string;
  student_id?: string | null;
  matricula: string;
  channel: string | null;
  risk_level: string | null;
  status: string;
  skip_reason: string | null;
  error: string | null;
  provider?: string | null;
  external_id?: string | null;
  correlation_id?: string | null;
  idempotency_key?: string | null;
  job_id?: string | null;
  campaign_id: string | null;
  delivery_status: string | null;
  delivery_event_id?: string | null;
  delivery_updated_at?: string | null;
  message_preview: string | null;
  created_at: string | null;
};

export type LogsResponse = { logs: InterventionLog[]; count?: number };

export type PreviewMessage = Record<string, unknown>;

export type MemberRole = "admin" | "coordinator" | "operator" | "viewer";

export type OrgMember = {
  id: string;
  display_name?: string | null;
  email: string;
  role: MemberRole;
  status: string;
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
  invite?: OrgInvite;
  invite_url?: string;
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
