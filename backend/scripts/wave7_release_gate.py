#!/usr/bin/env python3
"""Wave 7: evidence-based release decision. No migrations or deployments.

Exit 0 only when the requested stage's gates are backed by recorded evidence.
This gate never accepts comments or checked boxes as proof of tests.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

JOURNEYS = (
    "app_shell",
    "object_index",
    "student_360",
    "collections_360",
    "human_work",
    "universal_search",
)
VIEWPORTS = ("desktop", "mobile")
RELEASE_SCHEMA = 1
# Initial CI budgets only. Production budgets require validated baselines.
CI_PAGE_P95_MS = 12000
CI_API_P95_MS = 2500


def _positive_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and (
        math.isfinite(value) and 0 <= value
    )


def evaluate(data: dict, stage: str = "integration") -> dict:
    failed: list[str] = []
    if data.get("schema_version") != RELEASE_SCHEMA:
        failed.append("evidence_schema_unrecognized")
    if data.get("source") != "wave7_authenticated_live_asgi":
        failed.append("source_not_authenticated_asgi")
    if data.get("environment") not in ("ci", "staging"):
        failed.append("environment_not_isolated")
    if not data.get("signed_mfa_sessions"):
        failed.append("signed_mfa_sessions_not_verified")
    if not data.get("tenant_isolation"):
        failed.append("tenant_isolation_not_verified")
    if not data.get("rbac_denials"):
        failed.append("rbac_negative_cases_missing")
    if not data.get("integration_failure_isolation"):
        failed.append("provider_failure_not_isolated")
    if not data.get("no_critical_side_effects"):
        failed.append("unintended_financial_or_dispatch_side_effects")

    completed = set()
    for case in data.get("journeys", []):
        if not isinstance(case, dict):
            continue
        if case.get("status") == "passed" and case.get("authenticated") is True:
            completed.add((case.get("id"), case.get("viewport")))
    for journey in JOURNEYS:
        for viewport in VIEWPORTS:
            if (journey, viewport) not in completed:
                failed.append(f"journey_missing:{journey}:{viewport}")

    metrics = data.get("metrics") or {}
    for key, budget in (("page_p95_ms", CI_PAGE_P95_MS),
                        ("api_p95_ms", CI_API_P95_MS)):
        value = metrics.get(key)
        if not _positive_number(value):
            failed.append(f"metric_missing:{key}")
        elif value > budget:
            failed.append(f"metric_budget_exceeded:{key}")
    accessibility = data.get("accessibility") or {}
    if accessibility.get("serious_critical_count") != 0:
        failed.append("accessibility_serious_or_critical")

    if stage == "production":
        delivery = data.get("delivery") or {}
        for required in (
            "migration_compatibility_verified", "backup_restore_tested",
            "staging_p95_measured", "render_health_verified",
            "frontend_deployment_ready", "rollback_rehearsed",
            "manual_release_approval", "external_required_checks_green",
        ):
            if delivery.get(required) is not True:
                failed.append(f"production_evidence_missing:{required}")
        if data.get("environment") != "staging":
            failed.append("production_requires_staging_evidence")

    return {
        "stage": stage, "decision": "GO" if not failed else "NO_GO",
        "journeys_required": len(JOURNEYS) * len(VIEWPORTS),
        "journeys_verified": len(completed & {
            (journey, viewport) for journey in JOURNEYS for viewport in VIEWPORTS
        }),
        "failures": sorted(set(failed)),
        "does_not_deploy": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--stage", choices=("integration", "production"),
                        default="integration")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Evidence is not an object")
        verdict = evaluate(data, args.stage)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        verdict = {
            "stage": args.stage, "decision": "NO_GO",
            "failures": ["evidence_unreadable"],
            "does_not_deploy": True,
        }
        print(f"Evidence error: {type(error).__name__}", file=sys.stderr)
    output = json.dumps(verdict, sort_keys=True, indent=2, ensure_ascii=False)
    print(output)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    return 0 if verdict["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
