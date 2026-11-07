import type { ReactNode } from "react";
/** Presentation-only contracts; backend authorization remains the source of truth. */
export type RecordKind = "student" | "campaign" | "class" | "person" | "company" | "wallet" | "case" | "service" | (string & {});
export type RecordIdentity = { kind: RecordKind; id: string; title: string; subtitle?: string | null; caption?: string | null };
export type RecordProperty = {
  key: string; label: string; value: string | number | boolean | null | undefined;
  type?: "text" | "number" | "currency" | "percentage" | "date" | "datetime" | "boolean" | "status";
  /** A writable field must provide an explicitly authorized handler. */
  onEdit?: (value: string) => Promise<void>;
  editable?: boolean;
};
export type RecordPropertyGroup = { id: string; title: string; properties: RecordProperty[] };
export type RecordActivityEvent = {
  id: string; kind: "academic" | "contact" | "intervention" | "activity" | "risk" | "finance" | "status";
  at: string | null; title: string; origin: string;
  actor?: string | null; status?: string | null; description?: string | null;
  href?: string | null;
};
export type RecordRelation = { id: string; label: string; value: string; href?: string | null; type?: string };
export type RecordAction = { id: string; label: string; href?: string; onClick?: () => void; primary?: boolean; disabled?: boolean };
export type RecordSection = { id: string; label: string; content: ReactNode };
