"""Wave 7 read-only schema preflight must block unsafe or incomplete targets."""
from __future__ import annotations

import importlib.util
from pathlib import Path

source = Path(__file__).parents[1] / "scripts" / "wave7_schema_preflight.py"
spec = importlib.util.spec_from_file_location("wave7_schema_preflight", source)
assert spec and spec.loader
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def complete():
    return {
        "revision": "072_federated_search",
        "pg_trgm": True, "is_superuser": False, "bypass_rls": False,
        "rls": {
            table: {"rls": True, "force": True}
            for table in check.FORCE_RLS_TABLES
        },
        "indexes": sorted(check.REQUIRED_INDEXES),
        "relation_bytes": {"students": 1024},
    }


def test_compatible_schema_and_rls_pass_read_only():
    result = check.assess(complete())
    assert result["decision"] == "PASS"
    assert result["read_only"] is True
    assert result["violations"] == []


def test_missing_extension_index_or_forced_rls_prevents_release():
    state = complete()
    state["pg_trgm"] = False
    state["indexes"].remove("ix_search_students_name_trgm")
    state["rls"]["mira_object_views"]["force"] = False
    problems = check.assess(state)
    assert problems["decision"] == "BLOCK"
    assert "pg_trgm_not_installed" in problems["violations"]
    assert "missing_index:ix_search_students_name_trgm" in problems["violations"]
    assert "missing_forced_rls:mira_object_views" in problems["violations"]


def test_schema_drift_or_privileged_role_is_blocking():
    state = complete()
    state["revision"] = "066_object_index_views"
    state["is_superuser"] = True
    state["bypass_rls"] = True
    result = check.assess(state)
    assert set(result["violations"]) >= {
        "schema_revision_drift", "unsafe_database_runtime_role",
    }


def test_large_relation_warns_about_nonconcurrent_trigram_index_build():
    state = complete()
    state["relation_bytes"]["students"] = 2 * 1024 ** 3
    result = check.assess(state)
    assert result["decision"] == "PASS"
    assert "large_relation_index_build_requires_maintenance_approval" in result["warnings"]
