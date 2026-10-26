from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.outcomes import _require_model_approver


def test_model_approval_rejects_api_key_without_human_identity():
    with pytest.raises(HTTPException) as exc:
        _require_model_approver(SimpleNamespace(role="admin", user_id=None))
    assert exc.value.status_code == 403


def test_model_approval_requires_admin_role():
    with pytest.raises(HTTPException) as exc:
        _require_model_approver(SimpleNamespace(role="coordinator", user_id="user-1"))
    assert exc.value.status_code == 403


def test_model_approval_accepts_identified_admin_session():
    _require_model_approver(SimpleNamespace(role="admin", user_id="user-1"))
