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
        # Channel eligibility is already checked against the same student-level
        # preferences and contact data. Union channels recommended by different
        # groups; global blocks remain in blocked_reasons and are applied upstream.
        current["eligible_channels"] = sorted(
            set(current.get("eligible_channels", [])) | set(record.get("eligible_channels", []))
        )
        current["blocked_reasons"] = sorted(
            set(current.get("blocked_reasons", [])) | set(record.get("blocked_reasons", []))
        )
        current["internal_action_only"] = bool(
            current.get("internal_action_only") and record.get("internal_action_only")
        )
        hard_blocks = {"global_opt_out", "recent_intervention"}
        if hard_blocks.intersection(current["blocked_reasons"]):
            current["eligible_channels"] = []
        for channel in ("email", "whatsapp", "sms"):
            if f"preference_blocked:{channel}" in current["blocked_reasons"]:
                current["eligible_channels"] = [
                    item for item in current["eligible_channels"] if item != channel
                ]
        if "invalid_email" in current["blocked_reasons"]:
            current["eligible_channels"] = [
                item for item in current["eligible_channels"] if item != "email"
            ]
        if "invalid_whatsapp_contact" in current["blocked_reasons"]:
            current["eligible_channels"] = [
                item for item in current["eligible_channels"] if item != "whatsapp"
            ]
        if current["internal_action_only"]:
            current["eligible_channels"] = []
    return [merged[key] for key in sorted(merged)]


def hash_audience_snapshot(snapshot: list[dict[str, Any]]) -> str:
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
