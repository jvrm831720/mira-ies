import type { api } from "@/lib/api";
import { hasNavigationPermission } from "@/components/layout/navigation";

type WorkspaceProfile = Awaited<ReturnType<typeof api.me>> | undefined | null;

/** Same authorization gate for collection list, drawer and full record page. */
export function canReadCollectionRecord(me: WorkspaceProfile): boolean {
  if (!me) return false;
  const modules = Array.isArray(me.enabled_modules) ? me.enabled_modules : null;
  const institutionWithBilling = me.operation_profile === "institution" && !!modules?.includes("billing");
  const allowedProfile = ["collection", "debt_collection", "billing", "cobranca"].includes(me.operation_profile ?? "") ||
    institutionWithBilling;
  // Object and module grants must both pass; API/RLS remain authoritative.
  return allowedProfile && (!modules || modules.includes("billing")) &&
    hasNavigationPermission(me, "audit.view");
}
