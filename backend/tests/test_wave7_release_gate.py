"""Release must fail closed on missing journeys, metrics, approvals or environment."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

module_path = Path(__file__).parents[1] / "scripts" / "wave7_release_gate.py"
spec = spec_from_file_location("wave7_release_gate", module_path)
assert spec and spec.loader
gate = module_from_spec(spec)
spec.loader.exec_module(gate)


def evidence():
    return {
        "schema_version": 1,
        "source": "wave7_authenticated_live_asgi",
        "environment": "ci",
        "signed_mfa_sessions": True,
        "tenant_isolation": True,
        "rbac_denials": True,
        "integration_failure_isolation": True,
        "no_critical_side_effects": True,
        "accessibility": {"serious_critical_count": 0},
        "metrics": {"page_p95_ms": 3000, "api_p95_ms": 250},
        "journeys": [
            {"id": j, "viewport": v, "status": "passed", "authenticated": True}
            for j in gate.JOURNEYS for v in gate.VIEWPORTS
        ],
    }


def test_complete_ci_evidence_is_integration_go_without_claiming_deploy():
    outcome = gate.evaluate(evidence())
    assert outcome["decision"] == "GO"
    assert outcome["journeys_verified"] == 12
    assert outcome["does_not_deploy"]


def test_no_go_on_missing_mobile_or_failed_authentication():
    data = evidence()
    data["journeys"] = data["journeys"][:-1]
    assert "journey_missing:universal_search:mobile" in gate.evaluate(data)["failures"]
    data = evidence()
    data["signed_mfa_sessions"] = False
    assert gate.evaluate(data)["decision"] == "NO_GO"


def test_no_go_on_missing_metrics_bad_latency_or_serious_accessibility():
    data = evidence()
    data["metrics"].pop("api_p95_ms")
    assert "metric_missing:api_p95_ms" in gate.evaluate(data)["failures"]
    data = evidence()
    data["metrics"]["page_p95_ms"] = 999_999
    assert "metric_budget_exceeded:page_p95_ms" in gate.evaluate(data)["failures"]
    data = evidence()
    data["accessibility"]["serious_critical_count"] = 1
    assert "accessibility_serious_or_critical" in gate.evaluate(data)["failures"]


def test_no_go_on_cross_tenant_and_failed_provider_isolation():
    data = evidence()
    data["tenant_isolation"] = False
    data["integration_failure_isolation"] = False
    faults = gate.evaluate(data)["failures"]
    assert "tenant_isolation_not_verified" in faults
    assert "provider_failure_not_isolated" in faults


def test_production_requires_staging_backup_rollback_and_human_approval():
    data = evidence()
    assert gate.evaluate(data, stage="production")["decision"] == "NO_GO"
    data["environment"] = "staging"
    data["delivery"] = {
        key: True for key in (
            "migration_compatibility_verified", "backup_restore_tested",
            "staging_p95_measured", "render_health_verified",
            "frontend_deployment_ready", "rollback_rehearsed",
            "manual_release_approval", "external_required_checks_green",
            "security_advisors_triaged", "public_definer_rpc_grants_reviewed",
        )
    }
    assert gate.evaluate(data, stage="production")["decision"] == "GO"
    data["delivery"]["backup_restore_tested"] = False
    assert "production_evidence_missing:backup_restore_tested" in (
        gate.evaluate(data, stage="production")["failures"]
    )
