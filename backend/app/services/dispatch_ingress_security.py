"""HMAC-authenticated connector data ingestion; source scoped, nonce replay safe."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.dispatch_core import audit, bind_tenant

SCOPES=frozenset({"authorization","financial","contacts","delivery"})


def secret_cipher() -> Fernet:
    key=get_settings().dispatch_source_encryption_key
    if not key:
        raise ValueError("DISPATCH_SOURCE_ENCRYPTION_KEY não configurada.")
    try:
        return Fernet(key.encode())
    except (TypeError,ValueError) as exc:
        raise ValueError("Chave de fontes inválida.") from exc


def check_source(source: str, scope: str) -> None:
    if scope not in SCOPES or not source or len(source)>80 or not all(
        ch.isascii() and (ch.isalnum() or ch in "_-.") for ch in source
    ):
        raise ValueError("Fonte ou escopo inválido.")


async def configure(db: AsyncSession,*,tenant_id:str,actor:str,source:str,scope:str)->dict:
    check_source(source,scope)
    secret=secrets.token_urlsafe(48)
    cipher=secret_cipher().encrypt(secret.encode()).decode()
    await bind_tenant(db,tenant_id)
    await db.execute(text("""
        INSERT INTO dispatch_source_credentials
            (id,tenant_id,source,scope,secret_ciphertext,configured_by)
        VALUES (:id,:tenant,:source,:scope,:cipher,:actor)
        ON CONFLICT (tenant_id,source,scope) DO UPDATE SET
            secret_ciphertext=EXCLUDED.secret_ciphertext,status='disabled',
            configured_by=EXCLUDED.configured_by,
            approved_by=NULL,approved_at=NULL,created_at=now()
    """), {"id":str(uuid4()),"tenant":tenant_id,"source":source,
            "scope":scope,"cipher":cipher,"actor":actor})
    await audit(db,tenant_id=tenant_id,event_type="connector_key.configured",
                details={"source":source,"scope":scope,"actor":actor})
    await db.commit()
    return {"source":source,"scope":scope,"status":"disabled","secret_once":secret}


async def activate(db: AsyncSession,*,tenant_id:str,actor:str,source:str,scope:str,evidence:str)->dict:
    check_source(source,scope)
    if len(evidence.strip())<8:
        raise ValueError("Ativação exige evidência institucional.")
    await bind_tenant(db,tenant_id)
    row=(await db.execute(text("""
        SELECT configured_by FROM dispatch_source_credentials
        WHERE tenant_id=:tenant AND source=:source AND scope=:scope FOR UPDATE
    """), {"tenant":tenant_id,"source":source,"scope":scope})).mappings().first()
    if row is None:
        raise LookupError("Conector não cadastrado.")
    if row["configured_by"]==actor:
        raise ValueError("Ativação exige segundo administrador.")
    await db.execute(text("""
        UPDATE dispatch_source_credentials SET status='active',
            approved_by=:actor,approved_at=now()
        WHERE tenant_id=:tenant AND source=:source AND scope=:scope
    """), {"tenant":tenant_id,"source":source,"scope":scope,"actor":actor})
    await audit(db,tenant_id=tenant_id,event_type="connector_key.activated",
                details={"source":source,"scope":scope,"actor":actor,
                         "evidence_hash":hashlib.sha256(evidence.encode()).hexdigest()[:16]})
    await db.commit()
    return {"source":source,"scope":scope,"status":"active"}


async def disable(db: AsyncSession,*,tenant_id:str,actor:str,source:str,scope:str)->dict:
    check_source(source,scope)
    await bind_tenant(db,tenant_id)
    result=(await db.execute(text("""
        UPDATE dispatch_source_credentials SET status='disabled'
        WHERE tenant_id=:tenant AND source=:source AND scope=:scope RETURNING id
    """), {"tenant":tenant_id,"source":source,"scope":scope})).scalar_one_or_none()
    if not result:
        raise LookupError("Conector desconhecido.")
    await audit(db,tenant_id=tenant_id,event_type="connector_key.disabled",
                details={"source":source,"scope":scope,"actor":actor})
    await db.commit()
    return {"source":source,"scope":scope,"status":"disabled"}


async def list_sources(db: AsyncSession,tenant_id:str)->list[dict]:
    await bind_tenant(db,tenant_id)
    rows=await db.execute(text("""
        SELECT source,scope,status,configured_by,approved_by,approved_at,created_at
        FROM dispatch_source_credentials WHERE tenant_id=:tenant ORDER BY source,scope
    """), {"tenant":tenant_id})
    return [dict(r) for r in rows.mappings()]


def signature(secret:str,timestamp:str,nonce:str,method:str,path:str,body:bytes)->str:
    signed=".".join([timestamp,nonce,method.upper(),path,
                     hashlib.sha256(body).hexdigest()]).encode()
    return "sha256="+hmac.new(secret.encode(),signed,hashlib.sha256).hexdigest()


async def verify(db:AsyncSession,*,tenant_id:str,source:str,scope:str,request:Request)->None:
    try:
        check_source(source,scope)
    except ValueError as exc:
        raise HTTPException(status_code=403,detail=str(exc)) from exc
    heads=request.headers
    timestamp=heads.get("X-Mira-Timestamp") or ""
    nonce=heads.get("X-Mira-Nonce") or ""
    received=heads.get("X-Mira-Signature") or ""
    if (
        heads.get("X-Mira-Source")!=source or len(timestamp)>20
        or len(nonce)<16 or len(nonce)>80
        or not all(ch.isascii() and (ch.isalnum() or ch in "_-") for ch in nonce)
    ):
        raise HTTPException(status_code=401,detail="Fonte ou nonce inválido.")
    try:
        instant=int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401,detail="Timestamp inválido.") from exc
    if abs(time.time()-instant)>300:
        raise HTTPException(status_code=401,detail="Assinatura expirada.")
    raw=await request.body()
    if len(raw)>32768:
        raise HTTPException(status_code=413,detail="Evento de integração acima do limite.")
    await bind_tenant(db,tenant_id)
    encrypted=(await db.execute(text("""
        SELECT secret_ciphertext FROM dispatch_source_credentials
        WHERE tenant_id=:tenant AND source=:source AND scope=:scope AND status='active'
    """), {"tenant":tenant_id,"source":source,"scope":scope})).scalar_one_or_none()
    if not encrypted:
        raise HTTPException(status_code=403,detail="Fonte não aprovada no workspace.")
    try:
        key=secret_cipher().decrypt(encrypted.encode()).decode()
    except (InvalidToken,ValueError,TypeError) as exc:
        raise HTTPException(status_code=503,detail="Credencial de origem indisponível.") from exc
    expected=signature(key,timestamp,nonce,request.method,request.url.path,raw)
    if not received.startswith("sha256=") or not hmac.compare_digest(received,expected):
        raise HTTPException(status_code=401,detail="Assinatura de origem inválida.")
    inserted=(await db.execute(text("""
        INSERT INTO dispatch_source_nonces(tenant_id,source,scope,nonce)
        VALUES (:tenant,:source,:scope,:nonce)
        ON CONFLICT DO NOTHING RETURNING nonce
    """), {"tenant":tenant_id,"source":source,"scope":scope,"nonce":nonce})).scalar_one_or_none()
    if inserted is None:
        raise HTTPException(status_code=409,detail="Nonce já utilizado.")


async def prune_nonces(db:AsyncSession,tenant_id:str)->int:
    await bind_tenant(db,tenant_id)
    result=await db.execute(text("""
        DELETE FROM dispatch_source_nonces WHERE tenant_id=:tenant
          AND consumed_at<now()-interval '48 hours'
    """), {"tenant":tenant_id})
    await db.commit()
    return int(result.rowcount or 0)
