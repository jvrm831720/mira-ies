"""Wave 2: page-consistent multi-sort, counts and RBAC against database-backed APIs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.object_index import index_students
from app.api.collections import list_collection_cases
from app.models.student import Student, UploadBatch
from app.services.dispatch_core import bind_tenant


@pytest.mark.asyncio
async def test_student_multisort_across_full_tenant_and_pages(db_session, tenant_factory):
    a, _ = await tenant_factory(slug="wave2-index-a")
    b, _ = await tenant_factory(slug="wave2-index-b")
    for tenant, prefix, size in ((a, "A", 61), (b, "B", 8)):
        await db_session.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": tenant.id})
        batch = UploadBatch(tenant_id=tenant.id, filename="wave2.csv", original_filename="wave2.csv")
        db_session.add(batch)
        await db_session.flush()
        for i in range(size):
            db_session.add(Student(
                tenant_id=tenant.id, batch_id=batch.id, matricula=f"{prefix}-{i:03d}",
                nome=f"Aluno {i % 9:02d}", curso="Direito" if i % 2 else "Engenharia",
                risk_score=float(i % 100), risk_level="medio",
            ))
        await db_session.commit()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": a.id})
    auth = SimpleNamespace(tenant_id=a.id, role="coordinator", permissions=None, custom_role_id=None)
    kwargs = dict(
        q=None, course=None, risk_level=None, view="todos", filters=None, sort="name_asc",
        sorts="curso:asc,nome:desc", auth=auth, db=db_session,
    )
    pages = [await index_students(limit=25, offset=offset, **kwargs) for offset in (0, 25, 50)]
    assert [page["total"] for page in pages] == [61, 61, 61]
    assert [page["has_more"] for page in pages] == [True, True, False]
    keys = [row["id"] for page in pages for row in page["students"]]
    assert len(keys) == len(set(keys)) == 61
    names = [(row["curso"], row["nome"]) for page in pages for row in page["students"]]
    assert names == sorted(names, key=lambda item: (item[0], "".join(chr(65535 - ord(c)) for c in item[1])))
    assert all(not row["matricula"].startswith("B-") for page in pages for row in page["students"])

    view_only = SimpleNamespace(tenant_id=a.id, role="viewer",
                                permissions=frozenset({"students.view"}), custom_role_id="custom")
    with pytest.raises(HTTPException) as exc:
        await index_students(limit=25, offset=0, **{**kwargs, "auth": view_only, "sorts": "risk_score:desc"})
    assert exc.value.status_code == 403
    public = await index_students(limit=25, offset=0, **{
        **kwargs, "auth": view_only, "sorts": "nome:asc",
    })
    assert public["total"] == 61
    assert "risk_score" not in public["students"][0]


@pytest.mark.asyncio
async def test_financial_multisort_filters_across_pages_and_tenants(db_session, tenant_factory):
    a, _ = await tenant_factory(slug="wave2-cases-a")
    b, _ = await tenant_factory(slug="wave2-cases-b")
    for tenant, prefix, size in ((a, "A", 54), (b, "B", 7)):
        await bind_tenant(db_session, tenant.id)
        payloads = []
        for i in range(size):
            payloads.append({
                "id": str(uuid4()), "tenant": tenant.id, "ref": f"{prefix}-{i:03d}",
                "subject": f"subject-{i}", "status": "open" if i % 3 else "paid",
                "balance": f"{100 + i % 5}.00", "source": "wave2_integration",
                "verified": datetime.now(timezone.utc),
            })
        await db_session.execute(text("""
            INSERT INTO dispatch_obligations
            (id,tenant_id,external_ref,subject_type,subject_ref,status,balance,
             source,source_version,evidence_ref,verified_at)
            VALUES (:id,:tenant,:ref,'external',:subject,:status,:balance,
                    :source,1,'wave2-evidence',:verified)
        """), payloads)
        await db_session.commit()

    await bind_tenant(db_session, a.id)
    auth = SimpleNamespace(tenant_id=a.id)
    kwargs = dict(
        q="", status=None, statuses=None, sort="updated_at", desc=True,
        sorts="balance:desc,external_ref:asc",
        filters=json.dumps([
            {"key": "status", "op": "eq", "value": "open"},
            {"key": "source", "op": "eq", "value": "wave2_integration"},
        ]),
        auth=auth, db=db_session,
    )
    first = await list_collection_cases(limit=25, offset=0, **kwargs)
    second = await list_collection_cases(limit=25, offset=25, **kwargs)
    assert first["total"] == second["total"] == 36
    assert first["has_more"] and not second["has_more"]
    cases = first["items"] + second["items"]
    assert len(cases) == 36
    assert len({row["id"] for row in cases}) == 36
    assert all(row["external_ref"].startswith("A-") and row["status"] == "open" for row in cases)
    numeric_keys = [(-float(row["balance"]), row["external_ref"]) for row in cases]
    assert numeric_keys == sorted(numeric_keys)
    assert (await list_collection_cases(limit=10, offset=0, **{
        **kwargs,
        "filters": json.dumps([{"key": "status", "op": "eq", "value": "disputed"}]),
    }))["total"] == 0
