/** Wave 7 release control. This flag is only UX exposure, never authorization. */
export type RolloutMode = "off" | "canary" | "on";
export type RolloutConfig = { mode?: string; tenantIds?: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Existing user-facing experiences remain on by default. A canary with
 * missing or malformed tenant IDs fails closed; the original modules remain.
 */
export function isUnifiedExperienceEnabled(
  tenantId?: string | null,
  config: RolloutConfig = {
    mode: process.env.NEXT_PUBLIC_MIRA_UNIFIED_ROLLOUT,
    tenantIds: process.env.NEXT_PUBLIC_MIRA_CANARY_TENANTS,
  },
): boolean {
  const mode: string = config.mode || "on";
  if (mode === "off") return false;
  if (mode === "on") return true;
  if (mode !== "canary" || !tenantId || !UUID.test(tenantId)) return false;
  const allowlist = (config.tenantIds || "").split(",").map(id => id.trim().toLowerCase())
    .filter(id => UUID.test(id));
  return allowlist.includes(tenantId.toLowerCase());
}
