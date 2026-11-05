"""Per-workspace encrypted provider accounts, activation and native validation.

No global sender credentials are used by Dispatch. Provider connections are
bound to a tenant and activated only after a verified health probe and a
different administrator's approval.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.dispatch_core import audit, bind_tenant


def _fernet() -> Fernet:
    key = get_settings().dispatch_provider_encryption_key
    if not key:
        raise ValueError("DISPATCH_PROVIDER_ENCRYPTION_KEY não configurada.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("Chave de provedores inválida.") from exc


def validate_credentials(provider: str, data: dict[str, str]) -> dict[str, str]:
    if provider == "resend":
        required = {"api_key","from_email","webhook_secret"}
        if required - set(data):
            raise ValueError("Configuração Resend incompleta.")
        if not data["api_key"].startswith("re_") or not data["webhook_secret"].startswith("whsec_"):
            raise ValueError("Formato de credenciais Resend inválido.")
        _, sender = parseaddr(data["from_email"])
        if sender != data["from_email"] or "@" not in sender:
            raise ValueError("Remetente Resend inválido.")
    elif provider == "twilio":
        required = {"account_sid","auth_token","from_number"}
        if required - set(data):
            raise ValueError("Configuração Twilio incompleta.")
        if not data["account_sid"].startswith("AC") or not data["from_number"].startswith("+"):
            raise ValueError("Identificador de conta ou telefone Twilio inválido.")
        if len(data["auth_token"]) < 20:
            raise ValueError("Token Twilio inválido.")
    else:
        raise ValueError("Provedor não autorizado.")
    for value in data.values():
        if not isinstance(value,str) or not value.strip() or len(value)>400:
            raise ValueError("Credencial ausente ou excessivamente longa.")
    return {key:value.strip() for key,value in data.items() if key in required}


async def configure_provider(
    db: AsyncSession, *, tenant_id: str, provider: str, actor: str,
    data: dict[str, str],
) -> dict[str, Any]:
    validated=validate_credentials(provider,data)
    encrypted=_fernet().encrypt(json.dumps(validated).encode()).decode()
    await bind_tenant(db,tenant_id)
    row=(await db.execute(text("""
        INSERT INTO dispatch_provider_accounts
            (id,tenant_id,provider,credentials_ciphertext,configured_by)
        VALUES (:id,:tenant,:provider,:secret,:actor)
        ON CONFLICT (tenant_id,provider) DO UPDATE SET
            credentials_ciphertext=EXCLUDED.credentials_ciphertext,
            status='disabled', configured_by=EXCLUDED.configured_by,
            configured_at=now(), last_verified_at=NULL,
            credential_version=dispatch_provider_accounts.credential_version+1
        RETURNING provider,status,credential_version,configured_at
    """), {
        "id":str(uuid4()),"tenant":tenant_id,"provider":provider,
        "secret":encrypted,"actor":actor,
    })).mappings().one()
    await audit(db,tenant_id=tenant_id,event_type="provider.configured",
                details={"provider":provider,"actor":actor,
                         "version":row["credential_version"]})
    await db.commit()
    return dict(row)


async def _load_raw(
    db: AsyncSession, tenant_id: str, provider: str,
) -> dict[str, Any] | None:
    await bind_tenant(db,tenant_id)
    row=(await db.execute(text("""
        SELECT provider,status,credentials_ciphertext,configured_by,
               configured_at,credential_version,last_verified_at
        FROM dispatch_provider_accounts
        WHERE tenant_id=:tenant AND provider=:provider
    """), {"tenant":tenant_id,"provider":provider})).mappings().first()
    return dict(row) if row else None


async def load_provider(
    db: AsyncSession, *, tenant_id: str, provider: str,
    require_active: bool = True,
) -> dict[str, str] | None:
    row=await _load_raw(db,tenant_id,provider)
    if row is None or (require_active and (
        row["status"]!="active" or
        not row["last_verified_at"] or
        row["last_verified_at"] < datetime.now(timezone.utc)-timedelta(days=30)
    )):
        return None
    try:
        decrypted=_fernet().decrypt(row["credentials_ciphertext"].encode())
        data=json.loads(decrypted.decode())
        return validate_credentials(provider,data)
    except (ValueError,TypeError,InvalidToken,KeyError,json.JSONDecodeError):
        return None


async def list_providers(
    db: AsyncSession, tenant_id: str,
) -> list[dict[str, Any]]:
    await bind_tenant(db,tenant_id)
    result=await db.execute(text("""
        SELECT provider,status,credential_version,configured_at,last_verified_at
        FROM dispatch_provider_accounts WHERE tenant_id=:tenant ORDER BY provider
    """), {"tenant":tenant_id})
    return [dict(row) for row in result.mappings()]


async def verify_provider(
    db: AsyncSession, *, tenant_id: str, provider: str,
) -> dict[str, Any]:
    secrets=await load_provider(db,tenant_id=tenant_id,provider=provider,require_active=False)
    if not secrets:
        raise ValueError("Conta não configurada ou chave de criptografia indisponível.")
    # Pinned provider domains only; no user-supplied URL or SSRF.
    async with httpx.AsyncClient(timeout=8.0,follow_redirects=False) as client:
        if provider=="resend":
            response=await client.get(
                "https://api.resend.com/domains",
                headers={"Authorization":"Bearer "+secrets["api_key"]},
            )
            response.raise_for_status()
            info=response.json()
            domains=info.get("data",[]) if isinstance(info,dict) else []
            domain=secrets["from_email"].rsplit("@",1)[1].lower()
            good=any(
                isinstance(d,dict) and d.get("name","").lower()==domain
                and d.get("status")=="verified"
                for d in domains
            )
            if not good:
                raise ValueError("O domínio remetente não está verificado na Resend.")
        elif provider=="twilio":
            sid=secrets["account_sid"]
            response=await client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                auth=(sid,secrets["auth_token"]),
            )
            response.raise_for_status()
            data=response.json()
            if data.get("sid")!=sid or data.get("status")!="active":
                raise ValueError("Conta Twilio inativa ou inválida.")
            # A sender lookup is required as part of this provider's provisioning.
            response=await client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
                params={"PhoneNumber":secrets["from_number"],"PageSize":20},
                auth=(sid,secrets["auth_token"]),
            )
            response.raise_for_status()
            numbers=response.json().get("incoming_phone_numbers",[])
            if not any(x.get("phone_number")==secrets["from_number"] for x in numbers):
                raise ValueError("Número remetente não pertence à conta Twilio.")
        else:
            raise ValueError("Provedor desconhecido.")
    await bind_tenant(db,tenant_id)
    await db.execute(text("""
        UPDATE dispatch_provider_accounts SET last_verified_at=now()
        WHERE tenant_id=:tenant AND provider=:provider
    """), {"tenant":tenant_id,"provider":provider})
    await audit(db,tenant_id=tenant_id,event_type="provider.verified",
                details={"provider":provider})
    await db.commit()
    return {"verified":True,"provider":provider}


async def activate_provider(
    db: AsyncSession, *, tenant_id: str, provider: str,
    actor: str, evidence_ref: str,
) -> dict[str, str]:
    await bind_tenant(db,tenant_id)
    row=(await db.execute(text("""
        SELECT configured_by,last_verified_at,status
        FROM dispatch_provider_accounts
        WHERE tenant_id=:tenant AND provider=:provider FOR UPDATE
    """), {"tenant":tenant_id,"provider":provider})).mappings().first()
    if not row:
        raise LookupError("Conta de provedor não encontrada.")
    if row["configured_by"]==actor or not row["last_verified_at"] or (
        row["last_verified_at"]<datetime.now(timezone.utc)-timedelta(days=7)
    ):
        raise ValueError("Ativação exige verificação recente e segundo administrador.")
    if len(evidence_ref.strip())<8:
        raise ValueError("Informe referência do termo de ativação.")
    await db.execute(text("""
        UPDATE dispatch_provider_accounts SET status='active'
        WHERE tenant_id=:tenant AND provider=:provider
    """), {"tenant":tenant_id,"provider":provider})
    await audit(db,tenant_id=tenant_id,event_type="provider.activated",
                details={"provider":provider,"actor":actor,
                         "evidence_hash":__import__("hashlib").sha256(evidence_ref.encode()).hexdigest()[:16]})
    await db.commit()
    return {"provider":provider,"status":"active"}


async def disable_provider(
    db: AsyncSession, *, tenant_id: str, provider: str, actor: str,
) -> dict[str, str]:
    await bind_tenant(db,tenant_id)
    changed=(await db.execute(text("""
        UPDATE dispatch_provider_accounts SET status='disabled'
        WHERE tenant_id=:tenant AND provider=:provider RETURNING provider
    """), {"tenant":tenant_id,"provider":provider})).scalar_one_or_none()
    if not changed:
        raise LookupError("Provedor inexistente.")
    await audit(db,tenant_id=tenant_id,event_type="provider.disabled",
                details={"provider":provider,"actor":actor})
    await db.commit()
    return {"provider":provider,"status":"disabled"}
