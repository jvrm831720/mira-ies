"""Institutional metadata-driven financial sources and reconciliation endpoints.

No payment execution. Workspace staff authenticate through an active MFA session;
frontend never chooses tenant_id, raw Composio session or database table names.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import _require_ies
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.finance_reconciliation import (
    FinanceSourceProfile, FinanceStudentLink, FinanceObservation,
    FinanceReviewCase, FinanceReviewEvent, FinanceIngestionBatch,
)
from app.models.student import Student
from app.services import finance_reconciliation as engine
from app.services.composio.connections import ConnectionDenied
from app.services.composio.policy import ComposioPolicyDenied
from app.services.composio.client import ComposioSDKUnavailable

router = APIRouter(prefix="/native-academic/finance/reconciliation", tags=["Finance metadata reconciliation"])


def _actor(auth: AuthContext) -> str:
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Operação financeira exige sessão MFA AAL2.")
    return auth.user_id


async def _institution(auth: AuthContext, db: AsyncSession):
    engine.require_enabled()
    _actor(auth)
    await _require_ies(db, auth)


def _profile_json(row: FinanceSourceProfile):
    return {
        "id": row.id, "name": row.name, "source_kind": row.source_kind,
        "connected_account_id": row.connected_account_id, "tool_slug": row.tool_slug,
        "rows_path": row.rows_path, "field_map": row.field_map, "status_map": row.status_map,
        "student_lookup": row.student_lookup, "review_workflow": row.review_workflow,
        "enabled": row.enabled, "mapping_version": row.mapping_version,
        "created_at": row.created_at.isoformat(),
    }


class ProfileCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    source_kind: Literal["composio", "import"]
    connected_account_id: str | None = Field(default=None, max_length=120)
    tool_slug: str | None = Field(default=None, max_length=120)
    rows_path: str = Field(default="", max_length=240)
    field_map: dict[str, str] = Field(min_length=5, max_length=10)
    status_map: dict[str, str] = Field(default_factory=dict, max_length=40)
    review_workflow: dict | None = None
    student_lookup: Literal["mira_id", "verified_external"] = "mira_id"


class ProfileUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=3, max_length=100)
    rows_path: str = Field(default="", max_length=240)
    field_map: dict[str, str] = Field(min_length=5, max_length=10)
    status_map: dict[str, str] = Field(default_factory=dict, max_length=40)
    review_workflow: dict | None = None
    student_lookup: Literal["mira_id", "verified_external"] = "mira_id"
    enabled: bool = False


class LinkStudent(BaseModel):
    external_student_ref: str = Field(min_length=1, max_length=120)
    student_id: UUID


class PreviewRows(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class SuggestHeaders(BaseModel):
    headers: list[str] = Field(min_length=1, max_length=48)


class ExecuteRead(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class NewReview(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=5, max_length=500)


class TransitionReview(BaseModel):
    expected_version: int = Field(ge=1)
    step: str = Field(min_length=1, max_length=24, pattern="^[a-z][a-z0-9_]{0,23}$")
    note: str = Field(min_length=5, max_length=500)


@router.get("/profiles")
async def list_profiles(
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == auth.tenant_id,
    ).order_by(FinanceSourceProfile.name).limit(100))).scalars().all()
    return {"items": [_profile_json(row) for row in rows], "multiple_sources_supported": True}


@router.post("/profiles", status_code=201)
async def create_profile(
    body: ProfileCreate,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        config = engine.validate_profile(
            name=body.name, source_kind=body.source_kind,
            connected_account_id=body.connected_account_id,
            tool_slug=body.tool_slug, rows_path=body.rows_path,
            field_map=body.field_map, status_map=body.status_map,
            workflow=body.review_workflow, student_lookup=body.student_lookup,
        )
        row = FinanceSourceProfile(tenant_id=auth.tenant_id, created_by=auth.user_id,
                                   enabled=False, mapping_version=1, **config)
        db.add(row)
        await db.commit()
        return _profile_json(row)
    except (engine.ReconciliationDenied, ValueError) as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe perfil com este nome no workspace.") from exc


@router.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: UUID, body: ProfileUpdate,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        row = await engine.get_profile(db, auth.tenant_id, str(profile_id), lock=True)
        if body.expected_version != row.mapping_version:
            raise HTTPException(status_code=409, detail="Perfil alterado por outro operador.")
        config = engine.validate_profile(
            name=body.name, source_kind=row.source_kind,
            connected_account_id=row.connected_account_id, tool_slug=row.tool_slug,
            rows_path=body.rows_path, field_map=body.field_map,
            status_map=body.status_map, workflow=body.review_workflow,
            student_lookup=body.student_lookup,
        )
        for key, value in config.items():
            setattr(row, key, value)
        row.enabled = body.enabled
        row.mapping_version += 1
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return _profile_json(row)
    except engine.ReconciliationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Nome de perfil já utilizado.") from exc


@router.post("/profiles/{profile_id}/student-links", status_code=201)
async def link_student(
    profile_id: UUID, body: LinkStudent,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        profile = await engine.get_profile(db, auth.tenant_id, str(profile_id))
        if profile.student_lookup != "verified_external":
            raise HTTPException(status_code=409, detail="Perfil não usa vínculos externos verificados.")
        candidate = (await db.execute(select(Student.id).where(
            Student.tenant_id == auth.tenant_id, Student.id == str(body.student_id),
            Student.is_active.is_(True),
        ))).scalar_one_or_none()
        if candidate is None:
            raise HTTPException(status_code=404, detail="Aluno ativo não encontrado nesta instituição.")
        link = (await db.execute(select(FinanceStudentLink).where(
            FinanceStudentLink.tenant_id == auth.tenant_id,
            FinanceStudentLink.profile_id == str(profile_id),
            FinanceStudentLink.external_student_ref == body.external_student_ref,
        ))).scalar_one_or_none()
        if link is not None:
            if link.student_id != str(body.student_id):
                raise HTTPException(status_code=409, detail="Vínculo existente não pode ser trocado automaticamente.")
            return {"profile_id": str(profile_id), "student_id": link.student_id, "already_linked": True}
        db.add(FinanceStudentLink(
            tenant_id=auth.tenant_id, profile_id=str(profile_id),
            external_student_ref=body.external_student_ref, student_id=str(body.student_id),
            verified_by=auth.user_id,
        ))
        await db.commit()
        return {"profile_id": str(profile_id), "student_id": str(body.student_id), "already_linked": False}
    except engine.ReconciliationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflito de vínculo; recarregue os dados.") from exc


@router.post("/suggest-headers")
async def suggest_headers(
    body: SuggestHeaders,
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    return {"suggestions": engine.suggest_columns(body.headers),
            "automatic_application": False, "requires_confirmation": True}


@router.post("/profiles/{profile_id}/preview")
async def preview_import(
    profile_id: UUID, body: PreviewRows,
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        profile = await engine.get_profile(db, auth.tenant_id, str(profile_id))
        if profile.source_kind != "import":
            raise HTTPException(status_code=409, detail="Preview de registros externos não é permitido em perfil Composio.")
        return await engine.preview_rows(db, profile=profile, rows=body.rows)
    except engine.ReconciliationDenied as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/profiles/{profile_id}/import", status_code=201)
async def import_rows(
    profile_id: UUID, body: PreviewRows,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        profile = await engine.get_profile(db, auth.tenant_id, str(profile_id), lock=True)
        if profile.source_kind != "import":
            raise HTTPException(status_code=409, detail="Esta origem executa Composio; upload direto proibido.")
        return await engine.ingest_rows(
            db, tenant_id=auth.tenant_id, profile=profile, actor_id=auth.user_id,
            rows=body.rows, idempotency_key=idempotency_key, origin="import",
        )
    except engine.ReconciliationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Importação concorrente conflitou.") from exc


def _parse_csv(payload: bytes) -> list[dict[str, str]]:
    if not payload or len(payload) > 512 * 1024 or b"\x00" in payload:
        raise HTTPException(status_code=422, detail="CSV vazio, inválido ou acima de 512 KB.")
    try:
        text_data = payload.decode("utf-8-sig")
        source = csv.DictReader(io.StringIO(text_data), strict=True)
        if not source.fieldnames or len(source.fieldnames) > 48 or len(set(source.fieldnames)) != len(source.fieldnames):
            raise ValueError("Cabeçalho inválido.")
        rows = []
        for item in source:
            if len(rows) >= 100 or None in item or any(v is None for v in item.values()):
                raise ValueError("CSV excede 100 linhas ou possui colunas irregulares.")
            rows.append(item)
        return rows
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="CSV inválido. Use UTF-8, cabeçalhos únicos e até 100 linhas.") from exc


@router.post("/profiles/{profile_id}/import-csv", status_code=201)
async def import_csv(
    profile_id: UUID,
    file: UploadFile = File(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Somente CSV UTF-8 é aceito.")
    content = await file.read(512 * 1024 + 1)
    rows = _parse_csv(content)
    try:
        profile = await engine.get_profile(db, auth.tenant_id, str(profile_id), lock=True)
        if profile.source_kind != "import":
            raise HTTPException(status_code=409, detail="Perfil Composio não aceita CSV.")
        return await engine.ingest_rows(
            db, tenant_id=auth.tenant_id, profile=profile,
            actor_id=auth.user_id, rows=rows, origin="import",
            idempotency_key=idempotency_key,
        )
    except engine.ReconciliationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/profiles/{profile_id}/sync", status_code=201)
async def sync_composio(
    profile_id: UUID, body: ExecuteRead,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        return await engine.sync_composio_profile(
            db, tenant_id=auth.tenant_id, profile_id=str(profile_id),
            actor_id=auth.user_id, arguments=body.arguments, idempotency_key=idempotency_key,
        )
    except (engine.ReconciliationDenied, ConnectionDenied, ComposioPolicyDenied,
            ComposioSDKUnavailable, ValueError, TypeError) as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Consulta não autorizada, inválida ou não homologada.") from exc


@router.get("/profiles/{profile_id}/observations")
async def list_observations(
    profile_id: UUID, limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    await engine.get_profile(db, auth.tenant_id, str(profile_id))
    rows = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == auth.tenant_id,
        FinanceObservation.profile_id == str(profile_id),
    ).order_by(FinanceObservation.observed_at.desc()).limit(limit))).scalars().all()
    return {"items": [{
        "id": row.id, "student_id": row.student_id, "external_id": row.external_id,
        "correlation_key": row.correlation_key, "amount": str(row.amount),
        "paid_amount": str(row.paid_amount), "canonical_state": row.canonical_state,
        "raw_status": row.raw_status, "mapping_version": row.mapping_version,
        "observed_at": row.observed_at.isoformat(),
    } for row in rows], "settlement_confirmed": False}


@router.get("/discrepancies")
async def discrepancies(
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    return await engine.list_reconciliation(db, auth.tenant_id, limit=limit)


@router.get("/profiles/{profile_id}/batches")
async def batches(
    profile_id: UUID,
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    await engine.get_profile(db, auth.tenant_id, str(profile_id))
    rows = (await db.execute(select(FinanceIngestionBatch).where(
        FinanceIngestionBatch.tenant_id == auth.tenant_id,
        FinanceIngestionBatch.profile_id == str(profile_id),
    ).order_by(FinanceIngestionBatch.received_at.desc()).limit(50))).scalars().all()
    return {"items": [{
        "id": item.id, "origin": item.origin, "mapping_version": item.mapping_version,
        "row_count": item.row_count, "imported": item.imported_count,
        "unchanged": item.unchanged_count, "received_at": item.received_at.isoformat(),
    } for item in rows]}


@router.post("/profiles/{profile_id}/review-cases", status_code=201)
async def new_review(
    profile_id: UUID, body: NewReview,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        profile = await engine.get_profile(db, auth.tenant_id, str(profile_id))
        latest = (await db.execute(select(FinanceObservation).where(
            FinanceObservation.tenant_id == auth.tenant_id,
            FinanceObservation.profile_id == profile.id,
            FinanceObservation.external_id == body.external_id,
        ).limit(1))).scalar_one_or_none()
        if not latest:
            raise HTTPException(status_code=404, detail="Obrigação não encontrada na origem.")
        existing = (await db.execute(select(FinanceReviewCase).where(
            FinanceReviewCase.tenant_id == auth.tenant_id,
            FinanceReviewCase.profile_id == profile.id,
            FinanceReviewCase.external_id == body.external_id,
        ))).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "step": existing.step,
                    "version": existing.version, "already_exists": True}
        start = "open"
        case = FinanceReviewCase(
            tenant_id=auth.tenant_id, profile_id=profile.id, external_id=body.external_id,
            step=start, created_by=auth.user_id, updated_by=auth.user_id, version=1,
        )
        db.add(case)
        await db.flush()
        db.add(FinanceReviewEvent(tenant_id=auth.tenant_id, case_id=case.id,
                                  step=start, actor_id=auth.user_id, note=body.note))
        await db.commit()
        return {"id": case.id, "step": case.step, "version": case.version,
                "settlement_confirmed": False}
    except engine.ReconciliationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Revisão já criada por outro operador.") from exc


@router.post("/review-cases/{case_id}/transition")
async def transition_review(
    case_id: UUID, body: TransitionReview,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    case = (await db.execute(select(FinanceReviewCase).where(
        FinanceReviewCase.tenant_id == auth.tenant_id,
        FinanceReviewCase.id == str(case_id),
    ).with_for_update())).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    if case.version != body.expected_version:
        raise HTTPException(status_code=409, detail="Caso atualizado por outro operador.")
    profile = await engine.get_profile(db, auth.tenant_id, case.profile_id)
    allowed = profile.review_workflow.get("transitions", {}).get(case.step, [])
    if body.step not in allowed:
        raise HTTPException(status_code=409, detail="Transição não permitida pelo workflow deste workspace.")
    case.step = body.step
    case.version += 1
    case.updated_by = auth.user_id
    case.updated_at = datetime.now(timezone.utc)
    db.add(FinanceReviewEvent(tenant_id=auth.tenant_id, case_id=case.id,
                              step=body.step, actor_id=auth.user_id, note=body.note))
    await db.commit()
    return {"id": case.id, "step": case.step, "version": case.version,
            "settlement_confirmed": False}


@router.get("/review-cases/{case_id}/history")
async def review_history(
    case_id: UUID,
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    item = (await db.execute(select(FinanceReviewCase).where(
        FinanceReviewCase.id == str(case_id),
        FinanceReviewCase.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    events = (await db.execute(select(FinanceReviewEvent).where(
        FinanceReviewEvent.tenant_id == auth.tenant_id,
        FinanceReviewEvent.case_id == str(case_id),
    ).order_by(FinanceReviewEvent.recorded_at))).scalars().all()
    return {"case_id": str(case_id), "step": item.step,
            "events": [{
                "step": e.step, "actor_id": e.actor_id, "note": e.note,
                "recorded_at": e.recorded_at.isoformat(),
            } for e in events], "payment_status_not_changed": True}
