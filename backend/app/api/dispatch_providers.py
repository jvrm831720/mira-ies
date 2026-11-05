"""Tenant-scoped provider management. Credentials never leave the backend."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.services import dispatch_providers as providers

router = APIRouter(prefix="/dispatch/providers", tags=["Dispatch Providers"])


class ProviderSettings(BaseModel):
    credentials: dict[str,str] = Field(min_length=2, max_length=5)


class ProviderActivation(BaseModel):
    evidence_ref: str = Field(min_length=8,max_length=200)


def actor(auth: AuthContext) -> str:
    if not auth.user_id:
        raise HTTPException(status_code=403,detail="Ação restrita a usuário humano.")
    return auth.user_id


@router.get("")
async def list_provider_accounts(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return {"items":await providers.list_providers(db,auth.tenant_id)}


@router.put("/{provider}")
async def configure_provider_account(
    provider: Literal["resend","twilio"],
    body: ProviderSettings,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await providers.configure_provider(
            db,tenant_id=auth.tenant_id,provider=provider,
            actor=actor(auth),data=body.credentials,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@router.post("/{provider}/verify")
async def verify_provider_account(
    provider: Literal["resend","twilio"],
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await providers.verify_provider(db,tenant_id=auth.tenant_id,provider=provider)
    except (ValueError,LookupError) as exc:
        await db.rollback()
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        # Never echo sensitive remote HTTP errors, URLs, tokens or provider bodies.
        raise HTTPException(status_code=503,detail="Não foi possível verificar as credenciais do provedor.") from exc


@router.post("/{provider}/activate")
async def activate_provider_account(
    provider: Literal["resend","twilio"],
    body: ProviderActivation,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await providers.activate_provider(
            db,tenant_id=auth.tenant_id,provider=provider,
            actor=actor(auth),evidence_ref=body.evidence_ref,
        )
    except (ValueError,LookupError) as exc:
        await db.rollback()
        raise HTTPException(status_code=409,detail=str(exc)) from exc


@router.post("/{provider}/disable")
async def disable_provider_account(
    provider: Literal["resend","twilio"],
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await providers.disable_provider(
            db,tenant_id=auth.tenant_id,provider=provider,actor=actor(auth),
        )
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404,detail=str(exc)) from exc
