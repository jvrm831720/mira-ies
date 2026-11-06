/** Short-lived same-tab handoff. The server remains the authority for tenant, eligibility and consent. */
export const RETENTION_SELECTION_KEY = "mira:retention:selected-students:v1";
const MAX_AGE_MS = 10 * 60 * 1000;

export type RetentionSelection = {
  version: 1;
  tenantId: string;
  userId: string;
  ids: string[];
  campaign: string;
  createdAt: number;
};

export function serializeRetentionSelection(input: Omit<RetentionSelection, "version">): string {
  const ids = [...new Set(input.ids.filter(id => typeof id === "string" && id.length > 0 && id.length < 130))];
  if (!input.tenantId || !input.userId || !ids.length || ids.length > 100)
    throw new Error("Seleção inválida: escolha até 100 alunos.");
  return JSON.stringify({ ...input, ids, version: 1 });
}

/** Fail closed on corruption, stale state, another user, or another workspace. */
export function parseRetentionSelection(
  value: string | null, tenantId: string | undefined, userId: string | undefined,
  now = Date.now(),
): RetentionSelection | null {
  if (!value || !tenantId || !userId) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (typeof parsed !== "object" || parsed === null) return null;
    const data = parsed as Partial<RetentionSelection>;
    if (data.version !== 1 || data.tenantId !== tenantId || data.userId !== userId ||
        typeof data.createdAt !== "number" || data.createdAt > now ||
        now - data.createdAt > MAX_AGE_MS ||
        !Array.isArray(data.ids) || !data.ids.length || data.ids.length > 100 ||
        !data.ids.every(id => typeof id === "string" && id.length > 0 && id.length < 130) ||
        typeof data.campaign !== "string" || data.campaign.length > 160) return null;
    return data as RetentionSelection;
  } catch {
    return null;
  }
}
