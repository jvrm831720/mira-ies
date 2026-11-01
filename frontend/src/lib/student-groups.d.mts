export type StudentGroupSignalState =
  | "TRUE"
  | "FALSE"
  | "INDETERMINATE";

export type StudentGroupSignalPresentation = {
  label: string;
  explanation: string;
  tone: "success" | "muted" | "warning";
};

export function signalStatusPresentation(
  status: StudentGroupSignalState
): StudentGroupSignalPresentation;

export function cursorErrorKind(
  status: number
): "invalid" | "expired" | null;

export function hasCursorContinuation(page: {
  next_cursor?: string | null;
} | null | undefined): boolean;
