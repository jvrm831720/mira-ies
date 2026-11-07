import type { api } from "@/lib/api";

type WorkspaceProfile = Awaited<ReturnType<typeof api.me>> | undefined | null;

/** Same authorization gate for collection list, drawer and full record page. */
export function canReadCollectionRecord(me: WorkspaceProfile): boolean {
  if (!me) return false;
  const modules = Array.isArray(me.enabled_modules) ? me.enabled_modules : null;
  const institutionWithBilling = me.operation_profile === "institution" && !!modules?.includes("billing");
  const allowedProfile = ["collection", "debt_collection", "billing", "cobranca"].includes(me.operation_profile ?? "") ||
    institutionWithBilling;
  // Object and module grants must both pass; API/RLS remain authoritative.
  if (!allowedProfile || (modules && !modules.includes("billing"))) return false;
  if (me.permissions != null) return me.permissions.includes("audit.view");
  if (me.custom_role_id) return false;
  return me.role === "admin" || me.role === "coordinator";
}
