"""Wave 4C: metadata-driven financial imports, isolation, provenance and truth semantics.

Integration tests use PostgreSQL and synthetic data only; no remote Composio calls.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.finance_reconciliation import (
    FinanceIngestionBatch, FinanceObservation, FinanceSourceProfile,
    FinanceStudentLink, FinanceReviewCase, FinanceReviewEvent,
)
from app.models.student_services import StudentFinancialReference
from app.services import finance_reconciliation as fn

FIELDS = {
    "external_id": "Numero parcela", "student_reference": "Matricula",
    "amount": "Valor devido", "currency": "Moeda",
    "status": "Situacao", "label": "Descricao",
    "paid_amount": "Valor pago", "correlation_key": "Contrato",
}


def config(name: str = "Sistema A", *, lookup: str = "mira_id"):
    return fn.validate_profile(
        name=name, source_kind="import",
        field_map=FIELDS, status_map={"ABERTO": "open", "PAGO": "reported_paid",
                                      "ATRASADO": "overdue"},
        rows_path="", connected_account_id=None, tool_slug=None,
        workflow=None, student_lookup=lookup,
    )


def source(name: str, tenant_id: str, actor_id: str, *, lookup="mira_id"):
    return FinanceSourceProfile(
        tenant_id=tenant_id, created_by=actor_id,
        enabled=True, mapping_version=1, **config(name, lookup=lookup),
    )


def observation(student_ref: str, status: str = "ABERTO", *, total="100.00",
                external_id="t1", corr="MENSALIDADE-1"):
    return {
        "Numero parcela": external_id, "Matricula": student_ref,
        "Valor devido": total, "Moeda": "BRL", "Situacao": status,
        "Descricao": "Parcela acadêmica", "Valor pago": "0.00",
        "Contrato": corr,
    }


def test_profile_mapping_is_workspace_specific_and_never_executes_python():
    cfg = config()
    assert cfg["field_map"]["student_reference"] == "Matricula"
    assert cfg["enabled"] if "enabled" in cfg else True
    assert cfg["review_workflow"]["transitions"]["open"] == ["triage"]
    with pytest.raises(fn.ReconciliationDenied):
        fn.validate_profile(
            name="Nope", source_kind="import",
            field_map={**FIELDS, "python_script": "exec"}, status_map={},
            rows_path="", student_lookup="mira_id",
            connected_account_id=None, tool_slug=None, workflow=None,
        )


def test_custom_review_workflow_is_metadata_only():
    workflow = {
        "transitions": {"open": ["validacao"], "validacao": ["reviewed"],
                        "reviewed": []},
        "labels": {"open": "Recebido", "validacao": "Conferência", "reviewed": "Concluído"},
    }
    cfg = fn.validate_workflow(workflow)
    assert cfg["labels"]["validacao"] == "Conferência"
    with pytest.raises(fn.ReconciliationDenied):
        fn.validate_workflow({
            "transitions": {"open": ["settled"], "settled": ["unknown"]},
            "labels": {"open": "Pendente", "settled": "Pago"},
        })
    with pytest.raises(fn.ReconciliationDenied):
        fn.validate_workflow({
            "transitions": {"open": [{"call": "python"}], "reviewed": []},
            "labels": {"open": "Recebido", "reviewed": "Revisado"},
        })


@pytest.mark.parametrize("malicious", [
    {"password": "bank.password"}, {"routing": "bank_account"},
    {"foo": ["bad"]},
])
def test_mapping_rejects_secrets_and_incompatible_shapes(malicious):
    bad = dict(FIELDS)
    bad["external_id"] = next(iter(malicious.values()))
    with pytest.raises(fn.ReconciliationDenied):
        fn.validate_profile(
            name="Unsafe", source_kind="import", field_map=bad,
            status_map={"PAGO": "reported_paid"}, rows_path="",
            student_lookup="mira_id", connected_account_id=None,
            tool_slug=None, workflow=None,
        )


def test_unknown_financial_state_is_never_favorable():
    p = SimpleNamespace(field_map=FIELDS, status_map=config()["status_map"],
                        student_lookup="mira_id", source_kind="import")
    row = fn.normalize_rows([observation(str(uuid4()), "NÃO INFORMADO")], p)[0]
    assert row["canonical_state"] == "unknown"
    paid = fn.normalize_rows([observation(str(uuid4()), "PAGO")], p)[0]
    assert paid["canonical_state"] == "reported_paid"
    assert paid["paid_amount"] == Decimal("0.00")


def test_suggested_columns_require_confirmation_even_when_exact():
    suggested = fn.suggest_columns(["Matricula", "Numero parcela", "Valor devido", "Situacao"])
    assert suggested["student_reference"]["suggested_header"] == "Matricula"
    assert suggested["student_reference"]["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_two_sources_preserve_independent_truth_and_reconciliation_conflict(
    db_session, tenant_factory, monkeypatch,
):
    from app.models.student import Student, UploadBatch

    monkeypatch.setattr(fn, "get_settings", lambda: SimpleNamespace(
        student_finance_reconciliation_enabled=True,
        native_academic_enabled=True, native_academic_services_enabled=True,
    ))
    org, _ = await tenant_factory("finance-metadata-org", "Finance Metadata Org")
    upload = UploadBatch(tenant_id=org.id, filename="sample.csv",
                         original_filename="sample.csv", status="completed")
    db_session.add(upload)
    await db_session.flush()
    student = Student(tenant_id=org.id, batch_id=upload.id,
                      matricula="M-001", nome="Student Example", is_active=True)
    db_session.add(student)
    await db_session.flush()
    a = source("Sistema A", org.id, str(uuid4()))
    b = source("Sistema B", org.id, str(uuid4()))
    db_session.add_all([a, b])
    await db_session.commit()

    first = await fn.ingest_rows(
        db_session, tenant_id=org.id, profile=a, actor_id=a.created_by,
        rows=[observation(student.id, "ABERTO", external_id="same-id")],
        idempotency_key="invoice-import-00000001", origin="import",
    )
    assert first["imported"] == 1
    assert first["settlement_confirmed"] is False
    again = await fn.ingest_rows(
        db_session, tenant_id=org.id, profile=a, actor_id=a.created_by,
        rows=[observation(student.id, "ABERTO", external_id="same-id")],
        idempotency_key="invoice-import-00000001", origin="import",
    )
    assert again["deduplicated"] is True
    updated = await fn.ingest_rows(
        db_session, tenant_id=org.id, profile=b, actor_id=b.created_by,
        rows=[observation(student.id, "PAGO", external_id="same-id")],
        idempotency_key="invoice-import-00000002", origin="import",
    )
    assert updated["imported"] == 1
    snapshots = (await db_session.execute(select(StudentFinancialReference).where(
        StudentFinancialReference.tenant_id == org.id,
        StudentFinancialReference.student_id == student.id,
    ))).scalars().all()
    assert len(snapshots) == 2
    assert {item.source_status for item in snapshots} == {"open", "reported_paid"}
    summary = await fn.list_reconciliation(db_session, org.id)
    assert len(summary["items"]) == 1
    assert summary["items"][0]["result"] == "conflict"
    assert not summary["items"][0]["settlement_confirmed"]
    audit = (await db_session.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == org.id,
    ))).scalars().all()
    batches = (await db_session.execute(select(FinanceIngestionBatch).where(
        FinanceIngestionBatch.tenant_id == org.id,
    ))).scalars().all()
    assert len(audit) == 2
    assert len(batches) == 2


@pytest.mark.asyncio
async def test_cross_tenant_student_is_denied_before_writing(
    db_session, tenant_factory, monkeypatch,
):
    from app.models.student import Student, UploadBatch

    monkeypatch.setattr(fn, "get_settings", lambda: SimpleNamespace(
        student_finance_reconciliation_enabled=True,
        native_academic_enabled=True, native_academic_services_enabled=True,
    ))
    a, _ = await tenant_factory("finance-ten-a", "Tenant A")
    b, _ = await tenant_factory("finance-ten-b", "Tenant B")
    upload = UploadBatch(tenant_id=b.id, filename="b.csv", original_filename="b.csv",
                         status="completed")
    db_session.add(upload)
    await db_session.flush()
    alien = Student(tenant_id=b.id, batch_id=upload.id,
                    matricula="B001", nome="Student B", is_active=True)
    db_session.add(alien)
    profile = source("Workspace A", a.id, str(uuid4()))
    db_session.add(profile)
    await db_session.commit()
    workspace_id = a.id
    foreign_student_id = alien.id
    profile_actor_id = profile.created_by
    with pytest.raises(fn.ReconciliationDenied, match="outro workspace"):
        await fn.ingest_rows(
            db_session, tenant_id=workspace_id, profile=profile, actor_id=profile_actor_id,
            rows=[observation(foreign_student_id)], idempotency_key="cross-tenant-000001",
            origin="import",
        )
    await db_session.rollback()
    rows = (await db_session.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == workspace_id,
    ))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_verified_external_links_require_exact_profile_scope(
    db_session, tenant_factory, monkeypatch,
):
    from app.models.student import Student, UploadBatch

    monkeypatch.setattr(fn, "get_settings", lambda: SimpleNamespace(
        student_finance_reconciliation_enabled=True,
        native_academic_enabled=True, native_academic_services_enabled=True,
    ))
    org, _ = await tenant_factory("external-link-org", "External Links")
    upload = UploadBatch(tenant_id=org.id, filename="x.csv", original_filename="x.csv",
                         status="completed")
    db_session.add(upload)
    await db_session.flush()
    student = Student(tenant_id=org.id, batch_id=upload.id,
                      matricula="ST-1", nome="External Link", is_active=True)
    db_session.add(student)
    profile = source("External ERP", org.id, str(uuid4()), lookup="verified_external")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(FinanceStudentLink(
        tenant_id=org.id, profile_id=profile.id, student_id=student.id,
        external_student_ref="ERP-123", verified_by=str(uuid4()),
    ))
    await db_session.commit()
    result = await fn.ingest_rows(
        db_session, tenant_id=org.id, profile=profile, actor_id=profile.created_by,
        rows=[observation("ERP-123")], idempotency_key="external-link-000001", origin="import",
    )
    assert result["imported"] == 1
    assert not result["settlement_confirmed"]
