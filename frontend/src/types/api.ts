export type UploadStructureResponse = {
  filename: string;
  file_type: string;
  suggested_sheet?: string | null;
  requires_sheet_selection: boolean;
  persisted: false;
  sheets: Array<{
    name: string;
    rows: number;
    columns: string[];
    sample_rows: Array<Record<string, string>>;
    recognized_fields: Record<string, string>;
    required_fields_found: boolean;
    tabular: boolean;
  }>;
};

export type AuthResponse = {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  user?: { display_name?: string; email?: string; tenant_name?: string };
};

export type AuthActionResponse = { message: string };
export type MfaLoginChallenge = {
  mfa_required: boolean;
  mfa_enrollment_required: boolean;
  challenge_token: string;
  expires_in: number;
};
export type MfaStatus = { enabled: boolean; enabled_at: string | null; recovery_codes_remaining: number };
export type MfaEnrollment = { secret: string; qr_code: string; otpauth_uri: string };
export type MfaRecoveryCodes = { recovery_codes: string[] };
export type MfaPolicy = { require_mfa_all: boolean; required_roles: Array<"admin" | "coordinator" | "operator" | "viewer">; updated_at?: string | null };
export type MfaSession = {
  id: string;
  device_label: string;
  user_agent?: string | null;
  ip_address?: string | null;
  aal: number;
  created_at: string;
  expires_at: string;
  revoked_at?: string | null;
  current: boolean;
  active: boolean;
};
export type MfaSessionsResponse = { sessions: MfaSession[] };

export type RetentionWorkSummary = {
  pending: number;
  overdue_48h: number;
  failed: number;
  overdue_policy_hours: number;
  generated_at: string;
  definition: string;
};

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
    risk_score?: number | null;
    shap_summary?: string | null;
    shap_top_factors?: {
      summary?: string;
      top_3?: Array<{ feature?: string; label?: string }>;
      recommended_actions?: string[];
    } | null;
  }>;
};

export type StudentRisk = {
  id: string;
  nome?: string | null;
  matricula?: string | null;
  curso?: string | null;
  campus?: string | null;
  status_aluno?: string | null;
  semestre?: number | null;
  dias_atraso_boleto?: number | null;
  saldo_devedor?: number | null;
  status_financeiro?: string | null;
  telefone?: string | null;
  email?: string | null;
  communication_opt_out?: boolean;
  communication_preferences?: CommunicationPreferences;
  behavior_properties?: BehaviorProperties;
  engagement_score?: number | null;
  engagement_score_updated_at?: string | null;
  model_risk_score?: number | null;
  dynamic_risk_adjustment?: number;
  risk_score?: number | null;
  risk_level?: string | null;
  shap_summary?: string | null;
  shap_top_factors?: {
    summary?: string;
    top_3?: Array<{
      feature?: string;
      label?: string;
      value?: number;
      shap_value?: number;
      contribution?: string;
      impact_pct?: number;
      model_scope?: string;
      model_version?: string;
    }>;
    recommended_actions?: string[];
    rule_adjustments?: Array<{
      flag?: string;
      description?: string;
      delta_points?: number;
      evidence?: Record<string, unknown>;
      recommendation?: string | null;
      source?: string;
    }>;
    score_breakdown?: Record<string, number>;
    explanation_metadata?: {
      available?: boolean;
      status?: string;
      method?: string;
      reason_code?: string;
      explained_output?: string;
      calibration_included?: boolean;
      rules_included?: boolean;
      dynamic_adjustment_included?: boolean;
      model_scope?: string;
      model_version?: string;
    };
  } | null;
  recommended_actions?: string[] | null;
};

export type CommunicationChannel = "whatsapp" | "email" | "sms";
export type CommunicationTopic = "academic" | "retention" | "promotional";

export type CommunicationPreferences = {
  channels: Record<CommunicationChannel, boolean>;
  topics: Record<CommunicationTopic, boolean>;
};

export type CommunicationPreferenceUpdate = {
  opt_out?: boolean;
  channels?: Partial<Record<CommunicationChannel, boolean>>;
  topics?: Partial<Record<CommunicationTopic, boolean>>;
  source_reference?: string;
};

export type BehaviorProperties = {
  last_class_missed?: string | null;
  missed_classes_this_week?: number | null;
  current_module?: string | null;
  module_progress_pct?: number | null;
  recent_activity?: string | null;
  last_activity_at?: string | null;
  custom_properties?: Record<string, string | number | boolean | null>;
  message_fields?: string[];
};

export type BehaviorPropertiesResponse = {
  student_id: string;
  properties: BehaviorProperties;
  engagement_score?: number | null;
  engagement_score_updated_at?: string | null;
  model_risk_score?: number | null;
  risk_score?: number | null;
  risk_level?: RiskLevel;
  dynamic_risk_adjustment?: number;
};

export type SendTimeRecommendation = {
  student_id: string;
  channel: "whatsapp" | "email" | "sms";
  preferred_hour_local: number;
  timezone: string;
  next_send_at: string;
  confidence: "fallback" | "medium" | "high";
  reason: string;
  historical_attempts_at_hour: number;
  engagement_rate_pct_at_hour?: number | null;
  history_days: number;
};

export type OptimizedEnqueueResponse = {
  optimize_send_time: true;
  scheduled_count: number;
  skipped_count: number;
  failed_scheduling_count: number;
  scheduled_jobs: Array<{
    job_id: string;
    student_id: string;
    channel: string;
    status: string;
    scheduled_for: string;
    timezone: string;
    confidence: string;
    reason: string;
    historical_attempts_at_hour: number;
  }>;
  message: string;
};

export type CommunicationPreferenceResponse = {
  student_id?: string;
  opt_out: boolean;
  communication_opt_out?: boolean;
  communication_opted_out_at?: string | null;
  channels: Record<CommunicationChannel, boolean>;
  topics: Record<CommunicationTopic, boolean>;
  audit_events_created?: number;
};

export type ConsentAuditEvent = {
  id: string;
  event_type: string;
  channel?: CommunicationChannel | null;
  topic?: CommunicationTopic | null;
  previous_value?: boolean | null;
  new_value?: boolean | null;
  source: string;
  method: string;
  location: string;
  source_reference?: string | null;
  actor_user_id?: string | null;
  occurred_at: string;
  notes?: string | null;
};

export type ConsentAuditResponse = { count: number; events: ConsentAuditEvent[] };

export type ImportField =
  | "matricula"
  | "nome"
  | "curso"
  | "campus"
  | "status_aluno"
  | "turma"
  | "semestre"
  | "forma_ingresso"
  | "dias_atraso_boleto"
  | "recorrencia_atrasos"
  | "saldo_devedor"
  | "status_financeiro"
  | "dias_sem_login"
  | "presenca_percentual"
  | "nota_media"
  | "reprovacoes"
  | "telefone"
  | "email"
  | "communication_opt_out";

export type MultiUploadPreviewResponse = {
  items: Array<{
    index: number;
    filename: string;
    role?: string;
    valid: boolean;
    total_rows?: number;
    rows_to_import?: number;
    rows_to_reject?: number;
    existing_matches?: number;
    rows_that_will_be_created?: number;
    columns?: Array<{ key: string; label: string; suggested_field?: string | null; sample?: string }>;
    mapped_columns?: Record<string, string>;
    warnings?: string[];
    errors?: string[];
    error?: string;
  }>;
  summary: {
    files_received: number;
    files_valid: number;
    files_with_errors: number;
    distinct_matriculas_across_files: number;
    total_bytes: number;
    consolidated_students?: number;
    cross_file_conflicts?: number;
    duplicate_matriculas?: number;
  };
  persisted: boolean;
  cross_file_relationships_validated: boolean;
  consolidated_preview?: Array<{ matricula: string; fields: Record<string, string>; requires_review: boolean }>;
  conflicts?: Array<{ matricula: string; field: string; existing_value: string; incoming_value: string; filename: string; message: string }>;
  duplicate_matriculas?: Array<{ filename: string; role: string; matricula: string }>;
  message: string;
};

export type UploadPreviewResponse = {
  columns: Array<{
    key: string;
    label: string;
    suggested_field?: ImportField | null;
    sample?: string;
  }>;
  mapped_columns: Record<string, ImportField>;
  required_columns: string[];
  missing_required_columns: string[];
  recommended_columns: string[];
  missing_recommended_columns: string[];
  rows_received: number;
  rows_to_import: number;
  rows_that_will_be_created?: number;
  invalid_rows_count: number;
  invalid_rows: Array<{ line: number; message: string; severity?: string; column?: string; action?: string }>;
  issues?: Array<{ line: number | null; severity: "block" | "attention" | "info"; column?: string | null; message: string; action: string }>;
  selected_sheet?: string | null;
  duplicates_in_file: number;
  existing_matches: number;
  sample_rows: Array<Record<string, string | number | null>>;
  warnings: string[];
  warnings_total: number;
  quality_score: number;
  columns_original: string[];
  columns_recognized: string[];
  null_rates_pct: Record<string, number>;
  can_import: boolean;
  field_labels: Record<ImportField, string>;
  message?: string;
};

export type UploadHistoryItem = {
  id: string;
  filename: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  uploaded_at: string;
  processed_at?: string | null;
  error_message?: string | null;
};

export type UploadHistoryResponse = {
  items: UploadHistoryItem[];
  limit: number;
  offset: number;
  has_more: boolean;
};

export type UploadResponse = {
  message?: string;
  students_imported?: number;
  batch?: { id?: string };
  quality?: {
    rows_received?: number;
    rows_imported?: number;
    rows_discarded?: number;
    rows_created?: number;
    rows_updated?: number;
    duplicates_removed?: number;
    existing_matches?: number;
    quality_score?: number;
    warnings?: string[];
    warnings_total?: number;
    missing_recommended_columns?: string[];
  };
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

/** Status persistidos em InterventionLog (backend agents_common._VALID_STATUSES). */
export type InterventionStatus =
  | "planned"
  | "sending"
  | "sent"
  | "dry_run"
  | "unknown"
  | "failed"
  | "skipped";

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
  optimize_send_time?: boolean;
};

export type RetentionRunResult = {
  message?: string;
  campaign_id?: string | null;
  students_evaluated?: number;
  totals?: Partial<Record<"sent" | "dry_run" | "skipped" | "failed" | "unknown", number>>;
  by_channel?: Record<string, Partial<Record<string, number>>>;
};

export type RetentionJob = {
  id: string;
  tenant_id?: string;
  status: "scheduled" | "queued" | "running" | "retrying" | "paused" | "cancel_requested" | "cancelled" | "completed" | "failed" | "dead_letter";
  attempt?: number;
  max_attempts?: number;
  created_at?: number;
  updated_at?: number;
  scheduled_for?: number;
  paused_at?: number;
  resumed_at?: number;
  cancel_requested_at?: number;
  cancelled_at?: number;
  result?: RetentionRunResult;
  last_error?: string;
};

export type InterventionLog = {
  id: string;
  student_id?: string | null;
  matricula?: string | null;
  channel?: string | null;
  risk_level?: string | null;
  risk_score?: number | null;
  status: string;
  delivery_status?: string | null;
  decision_reason?: string | null;
  skip_reason?: string | null;
  error?: string | null;
  message_preview?: string | null;
  outcome?: string | null;
  outcome_at?: string | null;
  campaign_id?: string | null;
  created_at?: string | null;
};

export type LogsResponse = {
  logs: InterventionLog[];
  count?: number;
};

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

export type RetentionAnalyticsChannel = {
  messages_attempted: number;
  messages_sent: number;
  delivered_messages: number;
  bounced_messages: number;
  engaged_messages: number;
  clicked_messages: number;
  replied_messages: number;
  failed_messages: number;
  unknown_messages: number;
  unique_students_contacted: number;
  delivery_rate_pct: number | null;
  bounce_rate_pct: number | null;
  engagement_rate_pct: number | null;
  average_latency_ms: number | null;
  estimated_cost_brl_per_send: number | null;
  estimated_cost_brl_total: number | null;
  attribution: {
    attributed_students: number;
    retained_students: number;
    dropped_students: number;
    transferred_students: number;
    retention_rate_pct: number | null;
    attribution_coverage_pct: number | null;
  };
};

export type RetentionAnalytics = {
  period_days: number;
  period_start: string;
  generated_at: string;
  summary: {
    messages_sent: number;
    unique_students_contacted: number;
    attributed_students: number;
    retained_students: number;
    retention_rate_pct: number | null;
    attribution_coverage_pct: number | null;
    estimated_cost_brl_total: number | null;
    cost_configured_channels: number;
  };
  channels: Record<"whatsapp" | "email" | "sms", RetentionAnalyticsChannel>;
  providers: Array<{
    channel: string;
    provider: string;
    attempts: number;
    successes: number;
    failures: number;
    success_rate_pct: number | null;
    average_latency_ms: number | null;
  }>;
  engagement_events: Record<string, number>;
  attribution_note: string;
  cost_note: string;
};

export type PermanenceMetricCounts = {
  confirmed_outcomes: number;
  unique_students: number;
  rematriculados: number;
  active_confirmed: number;
  concluded: number;
  permanence_outcomes: number;
  evasion_outcomes: number;
  transfers_excluded: number;
  permanence_rate_pct: number | null;
  evasion_rate_pct: number | null;
  rematricula_share_pct: number | null;
  outcomes_with_academic_period: number;
  academic_period_coverage_pct: number | null;
  outcomes_with_source: number;
  source_coverage_pct: number | null;
};

export type PermanenceBreakdown = PermanenceMetricCounts & {
  key: string;
  label: string;
};

export type PermanenceAnalyticsRecord = {
  event_id: string;
  student_id?: string | null;
  matricula: string;
  student_name?: string | null;
  course?: string | null;
  outcome: string;
  outcome_label: string;
  outcome_at: string;
  academic_period?: string | null;
  academic_period_reported: boolean;
  outcome_source: string;
  intervention_count: number;
  campaigns: string[];
  channels: string[];
};

export type OperationalPermanenceMetrics = {
  records: number;
  messages_sent: number;
  unique_students_contacted: number;
  delivered_messages: number;
  engaged_messages: number;
  failed_messages: number;
  delivery_rate_pct: number | null;
  engagement_rate_pct: number | null;
};

export type OperationalPermanenceBreakdown = {
  key: string;
  label: string;
  records: number;
  messages_sent: number;
  unique_students_contacted: number;
  delivered_messages: number;
};

export type PermanenceAnalytics = {
  generated_at: string;
  period_days: number;
  filters_applied: {
    academic_period?: string | null;
    course?: string | null;
    campaign_id?: string | null;
    channel?: string | null;
  };
  options: {
    academic_periods: string[];
    courses: string[];
    campaigns: Array<{ id: string; name: string }>;
    channels: string[];
  };
  educational: {
    summary: PermanenceMetricCounts;
    by_academic_period: PermanenceBreakdown[];
    by_course: PermanenceBreakdown[];
    by_campaign: PermanenceBreakdown[];
    by_channel: PermanenceBreakdown[];
    source_events_total: number;
    records_total: number;
    records: PermanenceAnalyticsRecord[];
  };
  operational: {
    summary: OperationalPermanenceMetrics;
    by_campaign: OperationalPermanenceBreakdown[];
    by_channel: OperationalPermanenceBreakdown[];
    by_course: OperationalPermanenceBreakdown[];
    by_calendar_month: Array<{ key: string; label: string } & OperationalPermanenceMetrics>;
  };
  comparison: {
    status: "insufficient_data" | "available_descriptive";
    method: string;
    causal_claim: false;
    minimum_group_size: number;
    minimum_per_stratum: number;
    exposed_n: number;
    no_intervention_n: number;
    mixed_exposure_excluded: number;
    missing_baseline_risk_excluded: number;
    common_risk_bands?: string[];
    exposed_coverage_common_support_pct?: number;
    permanence_rate_exposed_pct: number | null;
    permanence_rate_no_intervention_standardized_pct: number | null;
    difference_percentage_points: number | null;
    reason: string;
  };
  methodology: {
    outcome_source: string;
    permanence_definition: string;
    intervention_window_days: number;
    causality: string;
    academic_period: string;
    operational_period: string;
    comparison: string;
  };
};

export type RiskHistoryAssessment = {
  id: string;
  student_id: string;
  tenant_id: string;
  student_name?: string | null;
  matricula?: string | null;
  course?: string | null;
  evaluated_at: string;
  score: number;
  risk_level: "baixo" | "medio" | "critico";
  model_version?: string | null;
  score_semantics_version: string;
  model_scope: string;
  score_basis: "final" | "legacy_adjusted";
  model_score?: number | null;
  dynamic_adjustment: number;
  explanation?: {
    available?: boolean;
    top_factors?: Array<{ feature?: string; label?: string; impact?: number; value?: number }>;
    summary?: string | null;
    rule_flags?: string[];
    rule_boost?: number;
    recommended_actions?: string[];
    confidence?: string;
    probability?: number;
  } | null;
  explanation_available: boolean;
  scoring_run_id: string;
  batch_id?: string | null;
};

export type RiskMovement = {
  student_id: string;
  student_name?: string | null;
  matricula?: string | null;
  course?: string | null;
  previous_score?: number | null;
  previous_risk_level?: string | null;
  previous_evaluated_at?: string | null;
  current_score: number;
  current_risk_level: string;
  current_evaluated_at: string;
  delta?: number | null;
  change_type:
    | "risco_aumentou"
    | "risco_diminuiu"
    | "sem_mudanca_relevante"
    | "sem_historico_comparavel"
    | "mudanca_modelo";
  model_version?: string | null;
  previous_model_version?: string | null;
  score_semantics_version: string;
  previous_score_semantics_version?: string | null;
  classification_changed: boolean;
};

export type RiskHistoryResponse = {
  tenant_id: string;
  period: { from: string; to: string };
  filters: { course?: string | null; risk_level?: string | null };
  total_assessments: number;
  students_with_assessments: number;
  temporal_data_truncated: boolean;
  temporal_rows_limit: number;
  comparison_counts: {
    increased: number;
    decreased: number;
    unchanged: number;
    model_changed: number;
    no_comparable_history: number;
    classification_changed: number;
  };
  timeline: Array<{
    bucket: string;
    model_scope: string;
    model_version: string;
    score_semantics_version: string;
    average_score: number;
    students_count: number;
    risk_distribution: { baixo: number; medio: number; critico: number; students_count: number };
  }>;
  courses: string[];
  movements: RiskMovement[];
  movements_truncated: boolean;
  assessments: RiskHistoryAssessment[];
  pagination: { page: number; page_size: number; total: number; pages: number };
  definition: string;
};

export type StudentRiskHistoryResponse = {
  student: { id: string; name: string; matricula: string; course?: string | null; tenant_id: string };
  period: { from: string; to: string };
  assessments: RiskHistoryAssessment[];
  total_assessments: number;
  pagination: { page: number; page_size: number; total: number; pages: number };
  interventions: Array<{
    id: string;
    created_at: string;
    channel?: string | null;
    status: string;
    risk_score?: number | null;
    risk_level?: string | null;
    decision_reason?: string | null;
    outcome?: string | null;
    outcome_at?: string | null;
  }>;
  explanation_note: string;
};


export type StudentGroupState = "TRUE" | "FALSE" | "INDETERMINATE";
export type StudentGroupCoverage = {
  evaluated: number;
  eligible: number;
  percentage: number | null;
  complete: boolean;
  has_indeterminate: boolean;
};
export type StudentGroupCatalogItem = {
  id: string;
  name: string;
  description: string;
  signal_ids: string[];
  inclusion_rule: string;
  limitations: string[];
  coverage_semantics: string;
};
export type StudentGroupsCatalogResponse = {
  catalog_version: string;
  count: number;
  groups: StudentGroupCatalogItem[];
  scope: string;
  tenant_id: string;
  notes: string[];
};
export type StudentGroupSummaryItem = {
  id: string;
  name: string;
  matched_count: number;
  false_count: number;
  indeterminate_count: number;
  coverage: StudentGroupCoverage;
  limitations: string[];
};
export type StudentGroupsSummaryResponse = {
  evaluated_at: string;
  scope: string;
  total_eligible: number;
  evaluated: number;
  groups: StudentGroupSummaryItem[];
  truncated: boolean;
  notes: string[];
};
export type StudentGroupSignalDefinition = {
  id: string;
  name: string;
  category: string;
  description: string;
  activation_rule: string;
  data_source: string;
  reliability: string;
  version: string;
};
export type StudentGroupDetailResponse = {
  id: string;
  name: string;
  description: string;
  catalog_version: string;
  signals_used: StudentGroupSignalDefinition[];
  inclusion_rule: string;
  metrics: {
    total_eligible: number;
    total_evaluated: number;
    total_belonging: number;
    total_not_belonging: number;
    total_indeterminate: number;
  };
  coverage: StudentGroupCoverage;
  limitations: string[];
  evaluated_at: string;
  truncated: boolean;
  notes: string[];
};
export type StudentGroupSignalEvaluation = {
  signal_id: string;
  status: StudentGroupState;
  evidence: Record<string, unknown>;
  reliability: string;
  signal_version: string;
  evaluated_at: string;
  limitations: string[];
};
export type StudentGroupMember = {
  student_id: string;
  name: string | null;
  group_id: string;
  membership_status: "TRUE";
  matched_signals: StudentGroupSignalEvaluation[];
  signals: StudentGroupSignalEvaluation[];
  evidence: Record<string, unknown>;
  limitations: string[];
  evaluated_at: string;
};
export type StudentGroupMembersResponse = {
  group_id: string;
  catalog_version: string;
  evaluated_at: string;
  ordering: string;
  count: number;
  members: StudentGroupMember[];
  next_cursor: string | null;
  has_more: boolean | null;
  truncated: boolean;
  notes: string[];
};


export type RetentionCampaignProposalStatus = "draft" | "in_review" | "changes_requested" | "approved" | "scheduled" | "running" | "paused" | "completed" | "cancelled" | "failed";
export type RetentionCampaignProposal = {
  id: string; tenant_id: string; status: RetentionCampaignProposalStatus; revision: number;
  title: string; objective: string; strategy: string; recommended_channels: string[];
  cadence_days: number[]; message_brief: string; source_group_ids: string[];
  source_catalog_version: string; recommendation_engine: string; source_evaluated_at: string;
  audience_total: number; outreach_eligible_count: number; blocked_count: number;
  internal_action_count: number; audience_hash: string; audience_snapshot: Array<Record<string, unknown>>;
  created_by?: string | null; created_at: string; updated_at: string;
  reviewed_by?: string | null; reviewed_at?: string | null; approved_by?: string | null; approved_at?: string | null;
  authorization_status: "not_verified" | "institution_attested"; authorization_basis?: string | null;
  authorization_reference?: string | null; authorization_attested_by?: string | null;
  authorization_attested_at?: string | null; scheduled_for?: string | null; schedule_timezone?: string | null; execution_enabled: false;
};
export type RetentionCampaignProposalsResponse = { count: number; proposals: RetentionCampaignProposal[] };
export type RetentionCampaignOpportunity = {
  group_id: string;
  group_name: string;
  matched_count: number;
  indeterminate_count: number;
  estimated_reach: { upper_bound: number; unit: string; validated_contacts: boolean; note: string };
  objective: string;
  strategy: string;
  recommended_channels: string[];
  cadence_days: number[];
  message_brief: string;
  safeguards: string[];
};
export type RetentionCampaignOpportunitiesResponse = {
  generated_at: string;
  catalog_version: string;
  recommendation_engine: string;
  is_ai_generated_copy: boolean;
  students_evaluated: number;
  total_active_students: number;
  opportunities_count: number;
  opportunities: RetentionCampaignOpportunity[];
  notes: string[];
};
export type RetentionCampaignProposalAudit = {
  proposal_id: string; count: number; events: Array<{
    id: string; event_type: string; actor_user_id?: string | null; revision: number;
    details: Record<string, unknown>; created_at: string;
  }>;
};

export type RetentionCampaignScheduleItem = {
  proposal_id: string;
  tenant_id: string;
  title: string;
  status: "scheduled" | "approved";
  scheduled_for: string | null;
  schedule_timezone: string | null;
  revision: number;
  execution_enabled: false;
  dispatch_created?: false;
};
export type RetentionCampaignScheduleResponse = {
  tenant_id: string;
  count: number;
  schedules: RetentionCampaignScheduleItem[];
  execution_enabled: false;
};
