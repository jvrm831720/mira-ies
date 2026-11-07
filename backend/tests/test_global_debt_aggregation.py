"""Wave 2 invariants: tenant isolation, consent and verified CPF gates."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import global_debt


def test_grant_rejects_empty_observations_and_short_evidence():
    from uuid import uuid4
    with pytest.raises(ValidationError):
        global_debt.GrantInput(account_id=uuid4(), student_id=uuid4(),
                               observation_ids=[], evidence_reference="case-1")


def test_aggregation_disabled_by_default(monkeypatch):
    monkeypatch.setattr(global_debt, "get_settings",
                        lambda: SimpleNamespace(global_student_debt_aggregation_enabled=False))
    with pytest.raises(HTTPException) as exc:
        global_debt._enabled()
    assert exc.value.status_code == 503


def test_unverified_email_never_authorizes_financial_disclosure():
    account = SimpleNamespace(identity_verified_at=None, email_verified_at=object())
    with pytest.raises(HTTPException) as exc:
        global_debt._verified(account)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_staff_must_have_mfa_and_real_user():
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await global_debt._staff(SimpleNamespace(user_id="a", session_id="b", aal=1), db)
    assert exc.value.status_code == 403


def test_no_global_tenant_finance_join_or_client_supplied_tenant():
    source = Path(global_debt.__file__).read_text()
    assert "FinanceObservation.tenant_id == auth.tenant_id" in source
    assert "FinanceObservation.student_id == str(body.student_id)" in source
    assert "GlobalDebtGrant.account_id == account.id" in source
    assert 'GlobalDebtGrant.state == "accepted"' in source
    assert 'global_student_debt_aggregation_enabled' in source
    assert "tenant_id: UUID" not in source
    assert "payment_execution_enabled" in source
