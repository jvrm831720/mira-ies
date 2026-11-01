/** Atividade operacional da Central de Trabalho (distinta de InterventionLog). */
export type WorkActivityStatus = "open" | "in_progress" | "completed" | "cancelled";
export type WorkActivityType = "follow_up" | "contact" | "review" | "other";

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
};

export type PatchWorkActivityBody = {
  title?: string;
  description?: string | null;
  assignee_user_id?: string | null;
  clear_assignee?: boolean;
  due_at?: string | null;
  clear_due?: boolean;
  status?: WorkActivityStatus;
};
