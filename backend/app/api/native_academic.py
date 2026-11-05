"""Native academic records + isolated student self-service.

Only manual source rows are writable in Wave 1. A student can see only the
academic and informational snapshots of their exact roster record. Risk models,
collections, agents, admin user sessions and message tools are never exposed.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.native_academic import (
    MiraAcademicRecord, MiraStudentPortalInvite, MiraStudentPortalSession,
)
from app.models.organization import Organization
from app.models.student import Student
from app.models.tenant import Tenant

router = APIRouter(prefix="/native-academic", tags=["MIRA Educação nativa"])
portal_router = APIRouter(prefix="/student-portal", tags=["Portal do Aluno"])

KINDS = ("enrollment", "attendance", "assessment", "fee")
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}\.[A-Za-z0-9_-]{42,64}$")
_PORTAL_COOKIE = "mira_portal_session"
_PORTAL_SECONDS = 8 * 60 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _make_token(tenant_id: str) -> str:
    return UUID(tenant_id).hex + "." + secrets.token_urlsafe(32)


def _tenant_from_token(raw: str) -> str:
    if not _TOKEN_RE.fullmatch(raw):
        raise HTTPException(status_code=401, detail="Acesso ao portal inválido ou expirado.")
    return str(UUID(hex=raw.split(".", 1)[0]))


def _require_native() -> None:
    if not get_settings().native_academic_enabled:
        raise HTTPException(status_code=503, detail="Módulo acadêmico ainda não habilitado.")


def _require_portal() -> None:
    if not get_settings().student_portal_enabled:
        raise HTTPException(status_code=503, detail="Portal do Aluno ainda não habilitado.")


async def _is_institution(db: AsyncSession, tenant: Tenant) -> bool:
    if not tenant.is_active:
        return False
    if tenant.organization_id:
        profile = (await db.execute(
            select(Organization.operation_profile).where(
                Organization.id == tenant.organization_id,
                Organization.is_active.is_(True),
            )
        )).scalar_one_or_none()
        return profile == "institution"
    return (tenant.segment or "").strip().lower() in {
        "institution", "higher_education", "university", "ies",
    }


async def _require_ies(db: AsyncSession, auth: AuthContext) -> None:
    if not await _is_institution(db, auth.tenant):
        raise HTTPException(status_code=403, detail="Exclusivo de instituições de ensino.")


async def _student(db: AsyncSession, tenant_id: str, student_id: str) -> Student:
    try:
        sid = str(UUID(student_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Aluno não encontrado.") from None
    result = await db.execute(select(Student).where(
        Student.id == sid,
        Student.tenant_id == tenant_id,
        Student.is_active.is_(True),
    ))
    student = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    return student


class AcademicRecordInput(BaseModel):
    kind: Literal["enrollment", "attendance", "assessment", "fee"]
    source_record_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    academic_period: str | None = Field(default=None, max_length=60)
    status: str | None = Field(default=None, max_length=60)
    event_date: date | None = None
    grade: Decimal | None = Field(default=None, ge=0)
    max_grade: Decimal | None = Field(default=None, gt=0)
    amount: Decimal | None = Field(default=None, ge=0)
    due_date: date | None = None
    currency: Literal["BRL"] | None = None

    @model_validator(mode="after")
    def validate_category(self):
        if self.kind == "attendance" and self.event_date is None:
            raise ValueError("Frequência exige a data do evento.")
        if self.kind == "assessment" and (self.grade is None or self.max_grade is None):
            raise ValueError("Avaliação exige nota e nota máxima.")
        if self.kind == "assessment" and self.grade is not None and self.max_grade is not None:
            if self.grade > self.max_grade:
                raise ValueError("Nota não pode exceder o máximo.")
        if self.kind == "fee" and (self.amount is None or self.due_date is None or self.currency != "BRL"):
            raise ValueError("Mensalidade exige valor, vencimento e moeda BRL.")
        if self.kind != "assessment" and (self.grade is not None or self.max_grade is not None):
            raise ValueError("Notas são exclusivas de avaliações.")
        if self.kind != "fee" and (self.amount is not None or self.due_date is not None or self.currency is not None):
            raise ValueError("Valores financeiros são exclusivos de mensalidades.")
        return self


class AcademicRecordBatch(BaseModel):
    records: list[AcademicRecordInput] = Field(min_length=1, max_length=100)


class PortalClaimInput(BaseModel):
    token: str = Field(min_length=70, max_length=140)


def _record_json(record: MiraAcademicRecord) -> dict:
    return {
        "id": record.id, "kind": record.kind, "source": record.source,
        "title": record.title, "academic_period": record.academic_period,
        "status": record.status,
        "event_date": record.event_date.isoformat() if record.event_date else None,
        "grade": str(record.grade) if record.grade is not None else None,
        "max_grade": str(record.max_grade) if record.max_grade is not None else None,
        "amount": str(record.amount) if record.amount is not None else None,
        "due_date": record.due_date.isoformat() if record.due_date else None,
        "currency": record.currency,
        "financial_snapshot_only": record.kind == "fee",
    }


async def _records(db: AsyncSession, tenant_id: str, student_id: str, kind: str | None = None) -> list[dict]:
    query = select(MiraAcademicRecord).where(
        MiraAcademicRecord.tenant_id == tenant_id,
        MiraAcademicRecord.student_id == student_id,
    )
    if kind is not None:
        if kind not in KINDS:
            raise HTTPException(status_code=422, detail="Tipo acadêmico desconhecido.")
        query = query.where(MiraAcademicRecord.kind == kind)
    rows = (await db.execute(query.order_by(
        MiraAcademicRecord.event_date.desc().nullslast(),
        MiraAcademicRecord.updated_at.desc(),
        MiraAcademicRecord.id.desc(),
    ).limit(200))).scalars().all()
    return [_record_json(row) for row in rows]


def _student_profile(student: Student, tenant_name: str) -> dict:
    # Never expose predictive risk, finances/debt, phone, SHAP, personal notes
    # or campaign data in self-service.
    return {
        "student_id": student.id, "name": student.nome,
        "registration": student.matricula,
        "course": student.curso, "campus": student.campus,
        "semester": student.semestre, "class_name": student.turma,
        "academic_status": student.status_aluno,
        "attendance_percentage": student.presenca_percentual,
        "grade_average": student.nota_media,
        "institution": tenant_name,
    }


@router.get("/status")
async def native_status(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await _require_ies(db, auth)
    return {
        "native_academic_enabled": get_settings().native_academic_enabled,
        "student_portal_enabled": get_settings().student_portal_enabled,
        "backend": "mira_postgresql",
        "frappe_runtime_required": False,
    }


@router.get("/students/{student_id}/records")
async def institution_records(
    student_id: str,
    kind: str | None = None,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    _require_native()
    await _require_ies(db, auth)
    student = await _student(db, auth.tenant_id, student_id)
    return {"student_id": student.id, "items": await _records(db, auth.tenant_id, student.id, kind)}


@router.put("/students/{student_id}/records")
async def import_manual_records(
    student_id: str, body: AcademicRecordBatch,
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Staff-reviewed ingestion only; no payments, score calculation or messaging."""
    _require_native()
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Exige uma sessão humana autenticada.")
    await _require_ies(db, auth)
    student = await _student(db, auth.tenant_id, student_id)
    seen = set()
    now = _now()
    for item in body.records:
        key = (item.kind, item.source_record_id)
        if key in seen:
            raise HTTPException(status_code=422, detail="Referência duplicada no lote.")
        seen.add(key)
        existing = (await db.execute(select(MiraAcademicRecord).where(
            MiraAcademicRecord.tenant_id == auth.tenant_id,
            MiraAcademicRecord.student_id == student.id,
            MiraAcademicRecord.kind == item.kind,
            MiraAcademicRecord.source == "manual",
            MiraAcademicRecord.source_record_id == item.source_record_id,
        ).with_for_update())).scalar_one_or_none()
        row = existing or MiraAcademicRecord(
            tenant_id=auth.tenant_id, student_id=student.id,
            kind=item.kind, source="manual", source_record_id=item.source_record_id,
        )
        for field in (
            "title", "academic_period", "status", "event_date", "grade",
            "max_grade", "amount", "due_date", "currency",
        ):
            setattr(row, field, getattr(item, field))
        row.updated_at = now
        if existing is None:
            db.add(row)
    await db.commit()
    return {"student_id": student.id, "records_received": len(body.records),
            "source": "manual", "live_messages_sent": False}


@router.post("/students/{student_id}/portal-invites", status_code=201)
async def create_portal_invite(
    student_id: str,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_portal()
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Exige administrador com sessão humana.")
    await _require_ies(db, auth)
    student = await _student(db, auth.tenant_id, student_id)
    # Wave 1: no automatic delivery. Operator must validate source identity and
    # deliver the one-time code securely. No proof of email ownership is inferred.
    if not (student.email or "").strip():
        raise HTTPException(status_code=422, detail="Aluno sem e-mail de contato cadastrado.")
    token = _make_token(auth.tenant_id)
    expiry = _now() + timedelta(minutes=15)
    db.add(MiraStudentPortalInvite(
        tenant_id=auth.tenant_id, student_id=student.id,
        token_hash=_hash_token(token), issued_by_user_id=auth.user_id,
        expires_at=expiry,
    ))
    await db.commit()
    return {"one_time_token": token, "expires_at": expiry.isoformat(),
            "delivery": "manual_only", "destination_verified": False}


def _portal_action(request: Request) -> None:
    # Custom header prevents ordinary cross-origin form CSRF. No permissive CORS.
    if request.headers.get("x-mira-portal-action") != "1":
        raise HTTPException(status_code=403, detail="Requisição de portal não autorizada.")


@dataclass
class PortalIdentity:
    tenant_id: str
    student: Student
    session: MiraStudentPortalSession
    tenant: Tenant


async def _portal_identity(request: Request, db: AsyncSession = Depends(get_db)) -> PortalIdentity:
    _require_portal()
    raw = request.cookies.get(_PORTAL_COOKIE, "")
    tenant_id = _tenant_from_token(raw)
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
    session = (await db.execute(select(MiraStudentPortalSession).where(
        MiraStudentPortalSession.tenant_id == tenant_id,
        MiraStudentPortalSession.token_hash == _hash_token(raw),
        MiraStudentPortalSession.revoked_at.is_(None),
        MiraStudentPortalSession.expires_at > _now(),
    ))).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=401, detail="Sessão do aluno inválida ou expirada.")
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or not await _is_institution(db, tenant):
        raise HTTPException(status_code=401, detail="Instituição indisponível.")
    student = await _student(db, tenant_id, session.student_id)
    return PortalIdentity(tenant_id, student, session, tenant)


@portal_router.post("/claim")
async def claim_portal_token(
    body: PortalClaimInput,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _require_portal()
    _portal_action(request)
    token = body.token.strip()
    tenant_id = _tenant_from_token(token)
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or not await _is_institution(db, tenant):
        raise HTTPException(status_code=401, detail="Convite inválido ou expirado.")
    invite = (await db.execute(select(MiraStudentPortalInvite).where(
        MiraStudentPortalInvite.tenant_id == tenant_id,
        MiraStudentPortalInvite.token_hash == _hash_token(token),
        MiraStudentPortalInvite.used_at.is_(None),
        MiraStudentPortalInvite.revoked_at.is_(None),
        MiraStudentPortalInvite.expires_at > _now(),
    ).with_for_update())).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=401, detail="Convite inválido ou expirado.")
    student = await _student(db, tenant_id, invite.student_id)
    invite.used_at = _now()
    session_token = _make_token(tenant_id)
    db.add(MiraStudentPortalSession(
        tenant_id=tenant_id, student_id=student.id,
        token_hash=_hash_token(session_token),
        expires_at=_now() + timedelta(seconds=_PORTAL_SECONDS),
    ))
    await db.commit()
    response.set_cookie(
        _PORTAL_COOKIE, session_token, max_age=_PORTAL_SECONDS,
        httponly=True, secure=get_settings().app_env not in {"development", "testing"},
        samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "student": _student_profile(student, tenant.name)}


@portal_router.get("/me")
async def portal_me(identity: PortalIdentity = Depends(_portal_identity)):
    return {"student": _student_profile(identity.student, identity.tenant.name)}


@portal_router.get("/records")
async def portal_records(
    kind: str | None = None,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    return {
        "student_id": identity.student.id,
        "items": await _records(db, identity.tenant_id, identity.student.id, kind),
        "financial_snapshot_only": True,
    }


@portal_router.post("/logout")
async def portal_logout(
    request: Request,
    response: Response,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _portal_action(request)
    identity.session.revoked_at = _now()
    await db.commit()
    response.delete_cookie(_PORTAL_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}
