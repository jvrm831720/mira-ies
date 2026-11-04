"""Pure helpers for deterministic and privacy-minimized proposal snapshots."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def deduplicate_audience_members(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one snapshot entry per student, merging matched group IDs."""
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        student_id = str(record["student_id"])
        current = merged.get(student_id)
        if current is None:
            current = {**record, "matched_group_ids": sorted(set(record.get("matched_group_ids", [])))}
            merged[student_id] = current
            continue
        current["matched_group_ids"] = sorted(
            set(current.get("matched_group_ids", [])) | set(record.get("matched_group_ids", []))
        )
        # A single global opt-out or recent contact always wins when duplicate
        # memberships are merged. Eligible channels are intersected, not unioned,
        # so a group cannot weaken a more restrictive snapshot.
        current["eligible_channels"] = sorted(
            set(current.get("eligible_channels", [])) & set(record.get("eligible_channels", []))
        )
        current["blocked_reasons"] = sorted(
            set(current.get("blocked_reasons", [])) | set(record.get("blocked_reasons", []))
        )
        if record.get("internal_action_only"):
            current["internal_action_only"] = True
            current["eligible_channels"] = []
    return [merged[key] for key in sorted(merged)]


def hash_audience_snapshot(snapshot: list[dict[str, Any]]) -> str:
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
