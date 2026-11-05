"""Public, email-verified organization provisioning for the first-run onboarding."""
from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mira_security import hash_password
from app.core.security import hash_api_key
from app.core.user_sessions import create_user_session
from app.api.mfa import create_login_challenge
from app.core.mfa_policy import user_requires_mfa
from app.db.session import get_db
from app.models.auth import AuthChallenge, User
from app.models.organization import Membership, ModuleEntitlement, Organization
from app.models.tenant import Tenant

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])
_MODULES = ("permanence", "data", "workspace", "mira_plan")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_digest(email: str, token: str) -> str:
    return hash_api_key(f"mira:token:onboarding:{email}:{token}")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return (slug or "instituicao")[:64].rstrip("-")


def _valid_cnpj(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    def digit(base: str, weights: list[int]) -> str:
        total = sum(int(number) * weight for number, weight in zip(base, weights))
        remainder = total % 11
        return str(0 if remainder < 2 else 11 - remainder)
    first = digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = digit(digits[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[-2:] == first + second


class CompleteOnboardingPayload(BaseModel):
    onboarding_token: str = Field(min_length=20, max_length=256)
    email: str = Field(min_length=5, max_length=255)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    job_title: str = Field(default="", max_length=120)
    organization_name: str = Field(min_length=2, max_length=255)
    trade_name: str = Field(default="", max_length=255)
    cnpj: str = Field(default="", max_length=32)
    website: str = Field(default="", max_length=255)
    institution_type: str = Field(default="higher_education", max_length=64)
    student_range: str = Field(default="", max_length=64)
    campuses: str = Field(default="", max_length=64)
    description: str = Field(default="", max_length=2000)
    data_sources: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Informe um e-mail válido.")
        return normalized

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_person_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Informe seu nome e sobrenome.")
        return normalized

    @field_validator("organization_name")
    @classmethod
    def validate_organization_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Informe o nome da instituição.")
        return normalized

    @field_validator("institution_type")
    @classmethod
    def validate_institution_type(cls, value: str) -> str:
        allowed = {"higher_education", "university_center", "university", "college", "technical", "other"}
        if value not in allowed:
            raise ValueError("Tipo de instituição inválido.")
        return value

    @field_validator("student_range")
    @classmethod
    def validate_student_range(cls, value: str) -> str:
        allowed = {"", "under_1000", "1000_5000", "5000_15000", "15000_50000", "over_50000"}
        if value not in allowed:
            raise ValueError("Faixa de alunos inválida.")
        return value

    @field_validator("campuses")
    @classmethod
    def validate_campuses(cls, value: str) -> str:
        allowed = {"", "1", "2_5", "6_20", "over_20"}
        if value not in allowed:
            raise ValueError("Quantidade de unidades inválida.")
        return value

    @field_validator("data_sources")
    @classmethod
    def validate_data_sources(cls, value: list[str]) -> list[str]:
        allowed = {"totvs_rm", "lyceum", "sponte", "sophia", "moodle", "canvas", "omie", "spreadsheets", "other"}
        if any(item not in allowed for item in value):
            raise ValueError("Uma das fontes de dados selecionadas é inválida.")
        return list(dict.fromkeys(value))

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if digits and not _valid_cnpj(digits):
            raise ValueError("Informe um CNPJ válido ou deixe o campo em branco.")
        return digits

    @field_validator("website")
    @classmethod
    def normalize_website(cls, value: str) -> str:
        value = value.strip()
        if value and not re.match(r"^https?://", value, re.I):
            value = "https://" + value
        if value and not re.match(r"^https?://[^/\s]+", value, re.I):
            raise ValueError("Informe um site válido.")
        return value


@router.post("/complete", status_code=201)
async def complete_onboarding(
    body: CompleteOnboardingPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Consume a one-time token issued only after successful email OTP verification."""
    now = _now()
    token_hash = _token_digest(body.email, body.onboarding_token)
    challenge = (
        await db.execute(
            select(AuthChallenge)
            .where(
                AuthChallenge.challenge_type == "onboarding_provision",
                AuthChallenge.identifier_hash == hash_api_key(f"mira:challenge:onboarding:{body.email}"),
                AuthChallenge.token_hash == token_hash,
                AuthChallenge.consumed_at.is_(None),
            )
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()
    if not challenge or challenge.expires_at <= now:
        raise HTTPException(status_code=401, detail="Sua validação expirou. Volte ao acesso e confirme seu e-mail novamente.")

    existing = (await db.execute(select(User.id).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Este e-mail já possui uma conta. Entre na sua conta para continuar.")

    if body.cnpj:
        duplicate = (await db.execute(
            select(Organization.id).where(
                Organization.country_code == "BR",
                Organization.tax_id_normalized == body.cnpj,
            )
        )).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=409, detail="Este CNPJ já está associado a uma organização na MIRA. Entre em contato com o administrador da instituição.")

    challenge.consumed_at = now
    organization = Organization(
        id=str(uuid4()),
        legal_name=body.organization_name.strip(),
        trade_name=body.trade_name.strip() or body.organization_name.strip(),
        country_code="BR",
        tax_id_normalized=body.cnpj or None,
        tax_id_display=body.cnpj or None,
        tax_id_source="user_provided" if body.cnpj else None,
        operation_profile="institution",
    )
    db.add(organization)
    await db.flush()

    base_slug = _slugify(body.trade_name or body.organization_name)
    slug = base_slug
    suffix = 2
    while (await db.execute(select(Tenant.id).where(Tenant.slug == slug))).scalar_one_or_none():
        slug = f"{base_slug[:58]}-{suffix}"
        suffix += 1

    tenant = Tenant(
        id=str(uuid4()),
        slug=slug,
        name=(body.trade_name.strip() or body.organization_name.strip())[:255],
        segment="higher_education",
        organization_id=organization.id,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    # Establish tenant context before writing tenant-scoped rows.
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant.id},
    )

    display_name = f"{body.first_name.strip()} {body.last_name.strip()}".strip()[:120]
    # MIRA's first-run access is passwordless (verified email OTP). Store an
    # unguessable hash so no reusable password is created from onboarding data.
    user = User(
        id=str(uuid4()),
        tenant_id=tenant.id,
        display_name=display_name,
        email=body.email,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        role="admin",
        is_active=True,
    )
    await db.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": user.id},
    )
    db.add(user)
    await db.flush()

    db.add(Membership(
        id=str(uuid4()),
        user_id=user.id,
        tenant_id=tenant.id,
        role="admin",
        status="active",
        origin="self_service_onboarding",
        joined_at=now,
    ))
    for module in _MODULES:
        db.add(ModuleEntitlement(
            id=str(uuid4()),
            tenant_id=tenant.id,
            module_key=module,
            status="enabled",
            source="default",
        ))

    organization.onboarding_profile = {
        "website": body.website or None,
        "institution_type": body.institution_type,
        "student_range": body.student_range or None,
        "campuses": body.campuses or None,
        "description": body.description.strip() or None,
        "data_sources": body.data_sources,
        "created_by_job_title": body.job_title.strip() or None,
        "onboarding_version": 1,
    }
    user.onboarding_completed_at = now

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível criar a organização. Verifique se o e-mail ou CNPJ já está em uso.")

    await db.refresh(user)
    await db.refresh(tenant)
    if await user_requires_mfa(db, user):
        return await create_login_challenge(db, user, tenant, purpose="enroll")

    token, ttl = await create_user_session(db, user, tenant, request, aal=1)
    await db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "user": {
            "display_name": user.display_name,
            "email": user.email,
            "tenant_name": tenant.name,
        },
        "organization": {
            "id": organization.id,
            "name": organization.legal_name,
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
        },
    }
