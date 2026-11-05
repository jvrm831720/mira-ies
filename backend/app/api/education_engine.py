"""MIRA Education Engine gateway: Render FastAPI to MIRA-owned Frappe sites.

No direct browser access to Frappe, no generic RPC proxy, no payments or writes
to academic/financial records. Each student is explicitly linked by tenant.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.education_engine import (
    TenantEducationEngineAudit, TenantEducationEngineConnection, TenantEducationEngineStudent,
)
from app.models.student import Student
from app.services.education_engine_client import (
    ALLOWED_COLLECTIONS, EducationEngineClient, EducationEngineError,
    checked_engine_url, checked_site,
)
from app.services.education_engine_secrets import (
    EducationEngineSecretError, encrypt_credential, decrypt_credential,
)

router = APIRouter(prefix="/education-engine", tags=["MIRA Education Engine"])


class ConnectionSetup(BaseModel):
    site_name: str = Field(min_length=2, max_length=200)
    api_key: str = Field(min_length=8, max_length=255)
    api_secret: str = Field(min_length=8, max_length=2048)

    @field_validator("api_key", "api_secret")
    @classmethod
    def safe_credential(cls, value: str) -> str:
        if any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
            raise ValueError("Credencial inválida.")
        return value


class StudentLinkSetup(BaseModel):
    student_id: UUID
    frappe_student_id: str = Field(min_length=1, max_length=180)

    @field_validator("frappe_student_id")
    @classmethod
    def safe_student_id(cls, value: str) -> str:
        if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("Identificador acadêmico inválido.")
        return value


def _environment_ready() -> tuple[str, str]:
    cfg = get_settings()
    if not cfg.mira_education_engine_enabled:
        raise HTTPException(
            status_code=503, detail="Motor acadêmico desabilitado até homologação.",
        )
    try:
        url = checked_engine_url(cfg.mira_education_engine_url or "", cfg.app_env)
        if not cfg.mira_education_engine_allowed_sites.strip():
            raise ValueError("Nenhum site autorizado no ambiente.")
        return url, cfg.mira_education_engine_allowed_sites
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Motor acadêmico sem configuração segura.") from exc


def _site_allowed(site_name: str, allowlist: str) -> str:
    try:
        return checked_site(site_name, allowlist)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Site não autorizado para este ambiente.") from exc


def _connection_output(row: TenantEducationEngineConnection | None) -> dict:
    return {
        "provider": "mira_education_engine",
        "configured": row is not None,
        "site_name": row.site_name if row else None,
        "enabled": bool(row.is_enabled) if row else False,
        "status": row.status if row else "not_configured",
        "verified_at": row.verified_at.isoformat() if row and row.verified_at else None,
        "last_error_code": row.last_error_code if row else None,
        "capabilities": {
            "students": "read_only", "enrollments": "read_only",
            "attendance": "read_only", "grades": "read_only",
            "fees": "unreconciled_read_only",
            "payments": "not_enabled", "agreements": "not_enabled",
            "self_service_portal": "not_enabled",
        },
    }


async def _connection(db: AsyncSession, tenant_id: str) -> TenantEducationEngineConnection | None:
    result = await db.execute(
        select(TenantEducationEngineConnection).where(
            TenantEducationEngineConnection.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


def _audit(auth: AuthContext, event: str, student_id: str | None = None) -> TenantEducationEngineAudit:
    return TenantEducationEngineAudit(
        tenant_id=auth.tenant_id, event_type=event,
        actor_user_id=auth.user_id, student_id=student_id,
    )


def _error(exc: EducationEngineError) -> HTTPException:
    return HTTPException(
        status_code=503 if exc.code in ("transport_failure", "upstream_unavailable") else 502,
        detail=f"Motor acadêmico indisponível ({exc.code}).",
    )


async def _client(
    db: AsyncSession, auth: AuthContext, *, allow_unverified: bool = False,
) -> tuple[TenantEducationEngineConnection, EducationEngineClient]:
    base_url, allowed = _environment_ready()
    row = await _connection(db, auth.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conexão acadêmica não cadastrada.")
    if not allow_unverified and (not row.is_enabled or row.status != "verified"):
        raise HTTPException(status_code=409, detail="Conexão acadêmica não está habilitada.")
    try:
        site = checked_site(row.site_name, allowed)
        token = decrypt_credential(row.encrypted_api_key)
        secret = decrypt_credential(row.encrypted_api_secret)
        client = EducationEngineClient(
            base_url=base_url, site=site, api_key=token, api_secret=secret,
            app_env=get_settings().app_env,
        )
    except (ValueError, EducationEngineSecretError) as exc:
        raise HTTPException(status_code=503, detail="Configuração do motor acadêmico inválida.") from exc
    return row, client


@router.get("/connection")
async def connection_status(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return {
        **_connection_output(await _connection(db, auth.tenant_id)),
        "environment_enabled": get_settings().mira_education_engine_enabled,
    }


@router.put("/connection", status_code=status.HTTP_200_OK)
async def configure_connection(
    body: ConnectionSetup,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _, allowed = _environment_ready()
    site = _site_allowed(body.site_name, allowed)
    row = await _connection(db, auth.tenant_id)
    if row and row.site_name != site:
        raise HTTPException(
            status_code=409,
            detail="Site já vinculado à IES. Troca de site exige migração auditada.",
        )
    try:
        encrypted_key = encrypt_credential(body.api_key)
        encrypted_secret = encrypt_credential(body.api_secret)
    except EducationEngineSecretError as exc:
        raise HTTPException(status_code=503, detail="Chave de proteção do backend não configurada.") from exc
    if row is None:
        row = TenantEducationEngineConnection(
            tenant_id=auth.tenant_id, site_name=site,
            encrypted_api_key=encrypted_key, encrypted_api_secret=encrypted_secret,
        )
        db.add(row)
    else:
        row.encrypted_api_key = encrypted_key
        row.encrypted_api_secret = encrypted_secret
        row.is_enabled = False
        row.status = "configured"
        row.verified_at = None
        row.last_error_code = None
    db.add(_audit(auth, "connection_configured"))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Site já reservado para outra instituição.",
        ) from exc
    return _connection_output(row)


@router.post("/connection/verify")
async def verify_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    row, client = await _client(db, auth, allow_unverified=True)
    try:
        if not await client.verify_service_account():
            raise EducationEngineError("unverified_identity")
    except EducationEngineError as exc:
        row.is_enabled = False
        row.status = "error"
        row.last_error_code = exc.code
        row.verified_at = None
        db.add(_audit(auth, "connection_verification_failed"))
        await db.commit()
        raise _error(exc) from exc
    finally:
        await client.aclose()
    row.is_enabled = False
    row.status = "verified"
    row.last_error_code = None
    row.verified_at = datetime.now(timezone.utc)
    db.add(_audit(auth, "connection_verified"))
    await db.commit()
    return _connection_output(row)


@router.post("/connection/enable")
async def enable_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _environment_ready()
    row = await _connection(db, auth.tenant_id)
    now = datetime.now(timezone.utc)
    verified = row.verified_at if row else None
    if verified and verified.tzinfo is None:
        verified = verified.replace(tzinfo=timezone.utc)
    if not row or row.status != "verified" or verified is None or verified < now - timedelta(hours=1):
        raise HTTPException(
            status_code=409, detail="Verifique novamente a conexão antes de habilitar.",
        )
    row.is_enabled = True
    db.add(_audit(auth, "connection_enabled"))
    await db.commit()
    return _connection_output(row)


@router.delete("/connection")
async def disable_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await _connection(db, auth.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conexão acadêmica inexistente.")
    row.is_enabled = False
    row.status = "disabled"
    db.add(_audit(auth, "connection_disabled"))
    await db.commit()
    return _connection_output(row)


@router.put("/student-links")
async def link_student(
    body: StudentLinkSetup,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    local_id = str(body.student_id)
    local = await db.execute(
        select(Student.id).where(Student.id == local_id, Student.tenant_id == auth.tenant_id),
    )
    if local.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado nesta instituição.")
    _row, client = await _client(db, auth)
    try:
        await client.student(body.frappe_student_id)
    except EducationEngineError as exc:
        raise _error(exc) from exc
    finally:
        await client.aclose()
    result = await db.execute(
        select(TenantEducationEngineStudent).where(
            TenantEducationEngineStudent.tenant_id == auth.tenant_id,
            TenantEducationEngineStudent.student_id == local_id,
        )
    )
    link = result.scalar_one_or_none()
    if link and link.frappe_student_id != body.frappe_student_id:
        raise HTTPException(status_code=409, detail="Vínculo existente exige revisão manual.")
    if link is None:
        db.add(TenantEducationEngineStudent(
            tenant_id=auth.tenant_id, student_id=local_id,
            frappe_student_id=body.frappe_student_id,
        ))
        db.add(_audit(auth, "student_link_created", local_id))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Aluno remoto já vinculado a outro cadastro.",
        ) from exc
    return {"student_id": local_id, "linked": True, "source": "mira_education_engine"}


async def _link(db: AsyncSession, auth: AuthContext, student_id: str) -> TenantEducationEngineStudent:
    try:
        local_id = str(UUID(student_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.") from exc
    check = await db.execute(
        select(Student.id).where(Student.id == local_id, Student.tenant_id == auth.tenant_id),
    )
    if check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    result = await db.execute(
        select(TenantEducationEngineStudent).where(
            TenantEducationEngineStudent.tenant_id == auth.tenant_id,
            TenantEducationEngineStudent.student_id == local_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Aluno ainda não vinculado ao motor acadêmico.")
    return link


@router.get("/students/{student_id}/profile")
async def student_profile(
    student_id: str,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    link = await _link(db, auth, student_id)
    _row, client = await _client(db, auth)
    try:
        profile = await client.student(link.frappe_student_id)
        return {"student_id": link.student_id, "source": "mira_education_engine", "profile": profile}
    except EducationEngineError as exc:
        raise _error(exc) from exc
    finally:
        await client.aclose()


@router.get("/students/{student_id}/{resource}")
async def student_records(
    student_id: str,
    resource: str,
    offset: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=30, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    if resource not in ALLOWED_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Recurso acadêmico não permitido.")
    link = await _link(db, auth, student_id)
    _row, client = await _client(db, auth)
    try:
        result = await client.records(
            resource, link.frappe_student_id, offset=offset, limit=limit,
        )
        return {"student_id": link.student_id, "resource": resource, **result}
    except EducationEngineError as exc:
        raise _error(exc) from exc
    finally:
        await client.aclose()


@router.get("/audit")
async def connection_audit(
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    results = await db.execute(
        select(TenantEducationEngineAudit).where(
            TenantEducationEngineAudit.tenant_id == auth.tenant_id,
        ).order_by(TenantEducationEngineAudit.occurred_at.desc()).limit(limit),
    )
    return {"events": [
        {
            "event_type": e.event_type, "student_id": e.student_id,
            "actor_user_id": e.actor_user_id, "occurred_at": e.occurred_at,
        }
        for e in results.scalars().all()
    ]}
