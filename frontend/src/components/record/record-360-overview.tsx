import { RecordProperties } from "./record-properties";
import { RecordRelations } from "./record-relations";
import type { RecordPropertyGroup, RecordRelation } from "./record-types";

/** Shared, presentation-only property + relation surface for all record domains. */
export function Record360Overview({
  groups, relations, compact = false, showRelations = true,
}: {
  groups: RecordPropertyGroup[]; relations: RecordRelation[];
  compact?: boolean; showRelations?: boolean;
}) {
  return <div className="space-y-4">
    <RecordProperties groups={groups} compact={compact} />
    {showRelations && <RecordRelations relations={relations} />}
  </div>;
}
