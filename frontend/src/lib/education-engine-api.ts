/** MIRA Education Engine — typed UI contract with the Render FastAPI gateway.
 * The browser never talks to Frappe directly and never receives Frappe tokens.
 */
import { educationEngineRequest } from "./api";

export type EducationEngineConnection = {
  provider: "mira_education_engine";
  configured: boolean;
  site_name: string | null;
  enabled: boolean;
  status: "not_configured" | "configured" | "verified" | "disabled" | "error" | string;
  verified_at: string | null;
  last_error_code: string | null;
  environment_enabled: boolean;
  capabilities: {
    students: string;
    enrollments: string;
    attendance: string;
    grades: string;
    fees: string;
    payments: string;
    agreements: string;
    self_service_portal: string;
  };
};

export type EducationEngineAuditEvent = {
  event_type: string;
  student_id: string | null;
  actor_user_id: string | null;
  occurred_at: string;
};

export type EducationEngineStudentProfile = {
  student_id: string;
  source: "mira_education_engine";
  profile: {
    name?: string;
    student_name?: string;
    first_name?: string;
    middle_name?: string;
    last_name?: string;
    student_email_id?: string;
    student_mobile_number?: string;
    enabled?: number | boolean;
    joining_date?: string;
  };
};

export type EducationEngineRow = Record<string, unknown> & { name?: string; student?: string };
export type EducationEngineResource = "attendance" | "grades" | "enrollments" | "fees";
export type EducationEngineRecords = {
  student_id: string;
  resource: EducationEngineResource;
  items: EducationEngineRow[];
  offset: number;
  limit: number;
  has_more: boolean;
  source: "mira_education_engine";
  financial_snapshot_only: boolean;
};

const endpoint = (segment: string) => "/" + segment;

export const educationEngine = {
  connection: () =>
    educationEngineRequest<EducationEngineConnection>("/connection"),

  configure: (body: { site_name: string; api_key: string; api_secret: string }) =>
    educationEngineRequest<EducationEngineConnection>("/connection", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  verify: () =>
    educationEngineRequest<EducationEngineConnection>("/connection/verify", {
      method: "POST",
    }),

  enable: () =>
    educationEngineRequest<EducationEngineConnection>("/connection/enable", {
      method: "POST",
    }),

  disable: () =>
    educationEngineRequest<EducationEngineConnection>("/connection", {
      method: "DELETE",
    }),

  audit: (limit = 30) =>
    educationEngineRequest<{ events: EducationEngineAuditEvent[] }>(
      "/audit?limit=" + encodeURIComponent(String(limit))
    ),

  linkStudent: (body: { student_id: string; frappe_student_id: string }) =>
    educationEngineRequest<{ student_id: string; linked: boolean; source: string }>(
      "/student-links", { method: "PUT", body: JSON.stringify(body) }
    ),

  studentProfile: (studentId: string) =>
    educationEngineRequest<EducationEngineStudentProfile>(
      endpoint("students") + "/" + encodeURIComponent(studentId) + "/profile"
    ),

  studentRecords: (
    studentId: string,
    resource: EducationEngineResource,
    offset = 0,
    limit = 30,
  ) =>
    educationEngineRequest<EducationEngineRecords>(
      endpoint("students") + "/" + encodeURIComponent(studentId) + "/" + resource +
      "?offset=" + encodeURIComponent(String(offset)) + "&limit=" + encodeURIComponent(String(limit))
    ),
};
