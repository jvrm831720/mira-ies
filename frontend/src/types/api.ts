export type AuthResponse = {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  user?: { display_name?: string; email?: string; tenant_name?: string };
};

export type AuthActionResponse = { message: string };

export type RiskSummary = {
  total_scored?: number;
  summary: { baixo: number; medio: number; critico: number };
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

export type StudentRisk = Record<string, unknown>;

export type CommunicationPreferenceResponse = { opt_out: boolean };

export type UploadResponse = Record<string, unknown>;

export type ModelInfo = {
  disclaimer?: string;
  training_data?: string;
};

export type AgentsStatus = Record<string, unknown>;

export type RetentionRunRequest = {
  dry_run?: boolean;
  student_ids?: string[];
  campaign_name?: string;
  campaign_id?: string;
};

export type RetentionRunResult = Record<string, unknown>;

export type LogsResponse = { logs: Array<Record<string, unknown>>; count?: number };

export type PreviewMessage = Record<string, unknown>;

export type MembersResponse = { members: Array<Record<string, unknown>> };

export type InvitesResponse = { invites: Array<Record<string, unknown>> };

export type InviteMemberRequest = { email: string; role: string };

export type InviteMemberResponse = Record<string, unknown>;

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
