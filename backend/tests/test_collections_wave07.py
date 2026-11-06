"""Wave 0.7: read-only collections are tenant scoped and have no side effects."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.collections import get_collection_case, list_collection_cases
from app.services.dispatch_core import bind_tenant


@pytest.mark.asyncio
async def test_collection_index_and_details_are_tenant_scoped(db_session, tenant_factory):
    privilege = (await db_session.execute(text(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
    ))).scalar_one()
    assert privilege is False

    a, _ = await tenant_factory(slug="collections-wave07-a")
    b, _ = await tenant_factory(slug="collections-wave07-b")
    ids = [a.id, b.id]
    cases = []
    for index, tenant in enumerate(ids):
        await bind_tenant(db_session, tenant)
        case_id = str(uuid4())
        cases.append(case_id)
        await db_session.execute(text("""
            INSERT INTO dispatch_obligations
            (id,tenant_id,external_ref,subject_type,subject_ref,status,balance,
             source,source_version,evidence_ref,verified_at)
            VALUES (:id,:tenant,:ref,'external',:subject,'open',:balance,
                    'test_source',1,'test-evidence',:verified)
        """), {
            "id": case_id, "tenant": tenant, "ref": f"CASE-{index}",
            "subject": f"subject-{index}", "balance": "120.00",
            "verified": datetime.now(timezone.utc),
        })
        await db_session.commit()

    auth = SimpleNamespace(tenant_id=ids[0])
    result = await list_collection_cases(
        q="", status=None, limit=25, offset=0, auth=auth, db=db_session
    )
    assert result["total"] == 1
    assert result["items"][0]["id"] == cases[0]
    assert result["items"][0]["balance"] == "120.00"

    detail = await get_collection_case(cases[0], auth=auth, db=db_session)
    assert detail["case"]["source"] == "test_source"
    assert detail["payment_events"] == []

    with pytest.raises(HTTPException) as exc:
        await get_collection_case(cases[1], auth=auth, db=db_session)
    assert exc.value.status_code == 404

    filtered = await list_collection_cases(
        q="", status="paid", limit=25, offset=0, auth=auth, db=db_session
    )
    assert filtered["total"] == 0
    await db_session.rollback()
