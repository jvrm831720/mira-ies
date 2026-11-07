/** Atividade operacional da Central de Trabalho (distinta de InterventionLog). */
export type WorkActivityStatus = "open" | "in_progress" | "completed" | "cancelled";
export type WorkActivityType = "follow_up" | "contact" | "review" | "other";
export type WorkPriority = "low" | "normal" | "high" | "urgent";
export type WorkOrigin = "manual" | "campaign";
export type WorkResultKind = "done" | "unreachable" | "deferred" | "referred";

export type WorkActivityAssignee = {
  id: string;
  display_name?: string | null;
  email?: string | null;
};

export type WorkActivity = {
  id: string;
  tenant_id: string;
  student_id?: string | null;
  intervention_log_id?: string | null;
  title: string;
  description?: string | null;
  activity_type: WorkActivityType | string;
  status: WorkActivityStatus | string;
  priority: WorkPriority | string;
  revision?: number;
  priority_reasons?: Array<{ code: string; label: string }>;
  result_semantics?: "human_work_only";
  origin_type: WorkOrigin | string;
  campaign_id?: string | null;
  assignee_user_id?: string | null;
  assignee?: WorkActivityAssignee | null;
  created_by_user_id?: string | null;
  due_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  overdue?: boolean;
};

export type WorkActivitiesResponse = {
  count: number;
  activities: WorkActivity[];
  note?: string;
};

export type WorkActivityEvent = {
  id: string;
  activity_id: string;
  actor_user_id?: string | null;
  event_type: string;
  payload?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type WorkActivityEventsResponse = {
  count: number;
  events: WorkActivityEvent[];
};

export type CreateWorkActivityBody = {
  title: string;
  description?: string | null;
  activity_type?: WorkActivityType;
  student_id?: string | null;
  intervention_log_id?: string | null;
  assignee_user_id?: string | null;
  due_at?: string | null;
  priority?: WorkPriority;
  campaign_id?: string | null;
};

export type CampaignActivityGenerationBody = {
  campaign_id: string;
  generation_key: string;
  student_ids: string[];
  title: string;
  description?: string | null;
  activity_type?: WorkActivityType;
  priority?: WorkPriority;
  assignee_user_id?: string | null;
  due_at?: string | null;
};

export type CampaignActivityGenerationResponse = {
  campaign_id: string;
  generation_key: string;
  count: number;
  created_count: number;
  reused_count: number;
  activities: WorkActivity[];
};

export type PatchWorkActivityBody = {
  title?: string;
  description?: string | null;
  assignee_user_id?: string | null;
  clear_assignee?: boolean;
  due_at?: string | null;
  clear_due?: boolean;
  status?: WorkActivityStatus;
  priority?: WorkPriority;
  student_id?: string | null;
  clear_student?: boolean;
  intervention_log_id?: string | null;
  clear_intervention_log?: boolean;
};

export type RecordResultBody = {
  note: string;
  kind?: WorkResultKind | null;
};

export type RecordResultResponse = {
  activity_id: string;
  status: string;
  intervention_log_id?: string | null;
  event_type: string;
  count: number;
  events: WorkActivityEvent[];
  note?: string;
};

/** Prefill when creating an activity from an intervention log row. */
export type CreateFromLogDraft = {
  student_id?: string | null;
  intervention_log_id: string;
  matricula?: string | null;
  channel?: string | null;
  decision_reason?: string | null;
  status?: string | null;
  suggested_title: string;
};

/** Timeline integrada do aluno (GET /students/{id}/work-timeline). */
export type WorkTimelineSource =
  | "risk_assessment"
  | "intervention_log"
  | "work_activity"
  | "engagement_event";

export type WorkTimelineItem = {
  source: WorkTimelineSource | string;
  id: string;
  at?: string | null;
  summary: string;
  refs?: Record<string, unknown> | null;
};

export type StudentWorkTimelineResponse = {
  student_id: string;
  tenant_id: string;
  count: number;
  limit: number;
  truncated?: boolean;
  items: WorkTimelineItem[];
  definition?: string;
};

export type WorkActivitySummary = {
  pending: number;
  overdue: number;
  completed_7d: number;
  unassigned: number;
  campaign_pending: number;
  urgent_pending: number;
  as_of: string;
};

/** Wave 5: one server-authoritative view over existing WorkActivity records. */
export type WorkPerspective = "mine" | "team" | "unassigned" | "history";
export type WorkInboxResponse = {
  view: WorkPerspective; as_of: string; total: number; limit: number; offset: number;
  has_more: boolean; next_offset: number | null; total_scope: "filtered_workspace_perspective";
  items: WorkActivity[];
};
export type WorkInboxCounts = {
  counts: Record<WorkPerspective, number>;
  scope: "full_tenant_with_user_perspective"; as_of: string;
};
export type ClaimWorkBody = { expected_revision: number; operation_key: string };
export type ResolveWorkBody = {
  expected_revision: number; operation_key: string;
  kind: WorkResultKind; note: string; next_due_at?: string | null;
};
export type WorkActionResponse = {
  activity: WorkActivity; event_id: string; idempotent_replay: boolean;
};
