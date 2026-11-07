"""Production startup and health checks must fail closed on schema drift."""
import pytest

from app.core.schema_readiness import (
    SchemaReadinessError, expected_schema_revision, validate_schema_revision,
)
from app.api import health as health_api


def test_single_known_head_matches_alembic_migration_chain():
    head = expected_schema_revision()
    assert head == "072_federated_search"
    validate_schema_revision(head, head)


@pytest.mark.parametrize("actual", [None, "", "071_work_inbox", "999_unknown"])
def test_missing_or_stale_revision_blocks_service(actual):
    with pytest.raises(SchemaReadinessError):
        validate_schema_revision(actual, expected_schema_revision())


@pytest.mark.asyncio
async def test_readiness_endpoint_reports_real_revision(monkeypatch):
    async def available():
        return "072_federated_search"
    monkeypatch.setattr(health_api, "assert_schema_ready", available)
    assert await health_api.readiness_check() == {
        "status": "ready", "schema_revision": "072_federated_search"
    }


@pytest.mark.asyncio
async def test_readiness_returns_503_without_leaking_db_errors(monkeypatch):
    async def drifted():
        raise SchemaReadinessError("Database secret SQL should be hidden")
    monkeypatch.setattr(health_api, "assert_schema_ready", drifted)
    result = await health_api.readiness_check()
    assert result.status_code == 503
    assert b"secret" not in result.body
    assert b"unready" in result.body

def test_demo_tenant_and_known_dev_key_are_never_bootstrapped_in_production():
    import ast
    from pathlib import Path

    file = Path(__file__).parents[1] / "app" / "main.py"
    module = ast.parse(file.read_text(encoding="utf-8"))
    lifespan = next(
        node for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan"
    )

    def walk(node, guarded=False):
        is_dev = (
            isinstance(node, ast.If)
            and ast.unparse(node.test) == "settings.app_env == 'development'"
        )
        protected = guarded or is_dev
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "slug" and isinstance(keyword.value, ast.Constant):
                    if keyword.value.value == "default":
                        assert protected, "Demo tenant must be dev-only"
                if keyword.arg == "api_key_hash" and "dev_api_key" in ast.unparse(keyword.value):
                    assert protected, "Known development API key must never be published"
        for child in ast.iter_child_nodes(node):
            walk(child, protected)

    walk(lifespan)
