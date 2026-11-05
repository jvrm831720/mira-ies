"""Tenant-admin operations for source-specific ingress HMAC credentials."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.services import dispatch_ingress_security as gate

router=APIRouter(prefix="/dispatch/source-keys",tags=["Dispatch Source Keys"])
Scope=Literal["authorization","financial","contacts","delivery"]

class Activation(BaseModel):
    evidence_ref: str=Field(min_length=8,max_length=200)

def actor(auth:AuthContext)->str:
    if not auth.user_id:
        raise HTTPException(status_code=403,detail="Administrador humano necessário.")
    return auth.user_id

@router.get("")
async def list_keys(
    auth:AuthContext=Depends(require_permission("settings.manage")),
    db:AsyncSession=Depends(get_db),
):
    return {"items":await gate.list_sources(db,auth.tenant_id)}

@router.post("/{scope}/{source}",status_code=201)
async def create_key(
    scope:Scope,source:str,
    auth:AuthContext=Depends(require_permission("settings.manage")),
    db:AsyncSession=Depends(get_db),
):
    try:
        return await gate.configure(db,tenant_id=auth.tenant_id,
                                    actor=actor(auth),source=source,scope=scope)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422,detail=str(exc)) from exc

@router.post("/{scope}/{source}/activate")
async def activate_key(
    scope:Scope,source:str,body:Activation,
    auth:AuthContext=Depends(require_permission("settings.manage")),
    db:AsyncSession=Depends(get_db),
):
    try:
        return await gate.activate(db,tenant_id=auth.tenant_id,
                                   actor=actor(auth),source=source,
                                   scope=scope,evidence=body.evidence_ref)
    except (ValueError,LookupError) as exc:
        await db.rollback()
        raise HTTPException(status_code=409,detail=str(exc)) from exc

@router.post("/{scope}/{source}/disable")
async def disable_key(
    scope:Scope,source:str,
    auth:AuthContext=Depends(require_permission("settings.manage")),
    db:AsyncSession=Depends(get_db),
):
    try:
        return await gate.disable(db,tenant_id=auth.tenant_id,
                                  actor=actor(auth),source=source,scope=scope)
    except (ValueError,LookupError) as exc:
        await db.rollback()
        raise HTTPException(status_code=404,detail=str(exc)) from exc
