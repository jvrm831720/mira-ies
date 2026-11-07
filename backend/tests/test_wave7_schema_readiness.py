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
