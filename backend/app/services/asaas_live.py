"""Official Asaas orchestration. All network writes explicitly gated and never retried.

The financial observation is the immutable input. Asaas charge is a separate
tenant-scoped projection; webhook delivery is stored before reconciliation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.asaas_live import (
    AsaasCharge, AsaasCustomerBinding, AsaasWebhookEvent, AsaasWebhookApplication,
)
from app.models.finance_reconciliation import FinanceObservation
from app.models.student import Student
from app.models.student_payments import AsaasWorkspaceDestination
from app.services import asaas_gateway as gateway
from app.services.dispatch_core import bind_tenant
from app.services.student_payments import draft_amount, asaas_split_rule


class AsaasFlowDenied(ValueError):
    pass


def _today() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def present(row: AsaasCharge) -> dict:
    return {
        "id": row.id, "student_id": row.student_id,
        "financial_observation_id": row.financial_observation_id,
        "method": row.method, "amount": str(row.amount), "currency": "BRL",
        "due_date": row.due_date.isoformat(), "environment": row.environment,
        "creation_state": row.creation_state,
        "payment_status": row.provider_payment_status,
        "split_status": row.provider_split_status,
        "payment_received_verified": row.payment_received_verified,
        "split_settled_verified": row.split_settled_verified,
        "needs_review": row.reconciliation_required,
        "destination_wallet_id": row.destination_wallet_id,
        "split_percent_of_net": 100,
    }


async def get_charge(db: AsyncSession, tenant_id: str, charge_id: str, *, lock=False) -> AsaasCharge:
    await bind_tenant(db, tenant_id)
    stmt = select(AsaasCharge).where(
        AsaasCharge.tenant_id == tenant_id, AsaasCharge.id == charge_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    charge = (await db.execute(stmt)).scalar_one_or_none()
    if charge is None:
        raise AsaasFlowDenied("Cobrança não encontrada neste workspace.")
    return charge


async def _check_observation(db: AsyncSession, tenant: str, observation: FinanceObservation):
    latest = (await db.execute(select(FinanceObservation.id).where(
        FinanceObservation.tenant_id == tenant,
        FinanceObservation.profile_id == observation.profile_id,
        FinanceObservation.external_id == observation.external_id,
    ).order_by(FinanceObservation.observed_at.desc(), FinanceObservation.id.desc()).limit(1))).scalar_one()
    if latest != observation.id:
        raise AsaasFlowDenied("Obrigação atualizada; use a observação mais recente.")
    try:
        return draft_amount(observation)
    except ValueError as exc:
        raise AsaasFlowDenied("Obrigação não está disponível para cobrança.") from exc


def financial_key(observation: FinanceObservation) -> str:
    return hashlib.sha256(
        (str(observation.tenant_id) + ":" + str(observation.profile_id) + ":" + observation.external_id).encode()
    ).hexdigest()


async def prepare_charge(
    db: AsyncSession, *, tenant_id: str, user_id: str,
    observation_id: str, method: str, due_date: date,
) -> dict:
    mode = gateway.environment(write=True)
    if method not in {"pix", "boleto"} or not (_today() <= due_date <= _today() + timedelta(days=180)):
        raise AsaasFlowDenied("Método ou vencimento fora da política de 180 dias.")
    await bind_tenant(db, tenant_id)
    observation = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant_id, FinanceObservation.id == observation_id,
    ))).scalar_one_or_none()
    if observation is None:
        raise AsaasFlowDenied("Obrigação não encontrada.")
    key = financial_key(observation)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"),
                     {"k": "asaas:charge:" + tenant_id + ":" + key})
    already = (await db.execute(select(AsaasCharge).where(
        AsaasCharge.tenant_id == tenant_id, AsaasCharge.financial_key == key,
    ))).scalar_one_or_none()
    if already:
        if already.financial_observation_id != observation_id or already.method != method:
            raise AsaasFlowDenied("Esta obrigação já possui uma cobrança; reconcilie antes de gerar outra.")
        return present(already)
    amount = await _check_observation(db, tenant_id, observation)
    dest = (await db.execute(select(AsaasWorkspaceDestination).where(
        AsaasWorkspaceDestination.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if not dest or (mode == "production" and dest.status != "verified") or dest.status == "rejected":
        raise AsaasFlowDenied("Carteira recebedora ainda não homologada para o ambiente selecionado.")
    issuer = get_settings().student_payments_asaas_issuer_wallet_id
    if not issuer or str(UUID(issuer)) == dest.wallet_id:
        raise AsaasFlowDenied("Conta emissora deve ser configurada e diferente do destino.")
    student = (await db.execute(select(Student).where(
        Student.tenant_id == tenant_id, Student.id == observation.student_id,
        Student.is_active.is_(True),
    ))).scalar_one_or_none()
    if student is None:
        raise AsaasFlowDenied("Aluno não ativo neste workspace.")
    binding = (await db.execute(select(AsaasCustomerBinding).where(
        AsaasCustomerBinding.tenant_id == tenant_id,
        AsaasCustomerBinding.student_id == student.id,
        AsaasCustomerBinding.issuer_environment == mode,
    ))).scalar_one_or_none()
    if binding is None:
        # No CPF from arbitrary raw_data or name-based fuzzy lookups.
        # The workspace's canonical student billing fields must be populated.
        data = student.custom_fields or {}
        cpf = data.get("billing_cpf") or data.get("cpf")
        customer_id = await gateway.get_or_create_customer(
            student_id=student.id, name=student.nome, cpf=cpf,
        )
        binding = AsaasCustomerBinding(
            tenant_id=tenant_id, student_id=student.id,
            asaas_customer_id=customer_id, issuer_environment=mode,
        )
        db.add(binding)
        await db.flush()
    result = AsaasCharge(
        tenant_id=tenant_id, financial_observation_id=observation.id,
        student_id=student.id, financial_key=key,
        method=method, amount=amount, currency="BRL",
        due_date=due_date, customer_id=binding.asaas_customer_id,
        destination_wallet_id=dest.wallet_id, destination_version=dest.version,
        environment=mode, external_reference="MIRA-" + str(uuid4()),
        creation_state="prepared", created_by=user_id,
    )
    db.add(result)
    await db.commit()
    return present(result)


async def _preflight_submit(db: AsyncSession, row: AsaasCharge, user_id: str):
    if row.environment != gateway.environment(write=True):
        raise AsaasFlowDenied("Ambiente mudou; a cobrança não pode ser emitida.")
    if row.environment == "production" and row.created_by == user_id:
        raise AsaasFlowDenied("Produção exige aprovação por segundo operador.")
    dest = (await db.execute(select(AsaasWorkspaceDestination).where(
        AsaasWorkspaceDestination.tenant_id == row.tenant_id,
    ))).scalar_one_or_none()
    if (dest is None or dest.wallet_id != row.destination_wallet_id
            or dest.version != row.destination_version
            or (row.environment == "production" and dest.status != "verified")):
        raise AsaasFlowDenied("Destino financeiro modificado ou não homologado.")
    obs = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == row.tenant_id,
        FinanceObservation.id == row.financial_observation_id,
    ))).scalar_one_or_none()
    if obs is None or (await _check_observation(db, row.tenant_id, obs)) != row.amount:
        raise AsaasFlowDenied("Saldo financeiro mudou após a preparação.")
    issuer = get_settings().student_payments_asaas_issuer_wallet_id
    if not issuer or str(UUID(issuer)) == row.destination_wallet_id:
        raise AsaasFlowDenied("Emissor Asaas não autorizado.")
    # Verify issuer identity against Asaas itself; static host, no tenant URL.
    remote = await gateway.request("GET", "/wallets/")
    issuer_remote = remote.get("walletId")
    if issuer_remote != issuer or issuer_remote == row.destination_wallet_id:
        raise AsaasFlowDenied("Carteira emissora do token não corresponde à configuração.")


async def submit_charge(db: AsyncSession, *, tenant_id: str, charge_id: str,
                        user_id: str) -> dict:
    row = await get_charge(db, tenant_id, charge_id, lock=True)
    if row.creation_state != "prepared":
        raise AsaasFlowDenied("Envio já iniciado; reconcilie, nunca repita o POST.")
    await _preflight_submit(db, row, user_id)
    payload = gateway.charge_payload(
        customer_id=row.customer_id, method=row.method,
        amount=row.amount, due_date=row.due_date,
        external_reference=row.external_reference,
        destination_wallet_id=row.destination_wallet_id,
    )
    row.creation_state = "submitting"
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()  # durable fence BEFORE the non-idempotent external POST
    try:
        remote = await gateway.request("POST", "/payments", data=payload)
    except gateway.GatewayRejected:
        row.creation_state = "rejected"
        row.reconciliation_required = True
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise AsaasFlowDenied("Provedor recusou a cobrança; intervenção necessária.") from None
    except gateway.GatewayInconclusive:
        row.creation_state = "unknown"
        row.reconciliation_required = True
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise AsaasFlowDenied("Resposta inconclusiva: consulte pela referência; não reenvie.") from None
    try:
        found_id = gateway.verify_payment_response(remote, row)
    except gateway.GatewayInconclusive:
        possible = remote.get("id")
        if isinstance(possible, str) and re.fullmatch(r"pay_[A-Za-z0-9_-]{4,72}", possible):
            row.asaas_payment_id = possible
        row.creation_state = "review"
        row.reconciliation_required = True
        await db.commit()
        raise AsaasFlowDenied("Cobrança criada mas Split ou dados não confirmados; reconciliação necessária.") from None
    row.asaas_payment_id = found_id
    row.creation_state = "created"
    row.provider_payment_status = str(remote.get("status", "UNKNOWN"))[:28]
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return present(row)


async def reconcile_charge(db: AsyncSession, *, tenant_id: str, charge_id: str) -> dict:
    gateway.environment()
    charge = await get_charge(db, tenant_id, charge_id, lock=True)
    if charge.environment != gateway.environment():
        raise AsaasFlowDenied("Ambiente diferente; conciliação bloqueada.")
    if charge.creation_state == "prepared":
        raise AsaasFlowDenied("Rascunho ainda não enviado à Asaas.")
    if not charge.asaas_payment_id:
        found = await gateway.request("GET", "/payments", params={
            "externalReference": charge.external_reference, "limit": 10,
        })
        matches = [x for x in found.get("data", [])
                   if isinstance(x, dict) and x.get("externalReference") == charge.external_reference]
        if len(matches) != 1:
            charge.creation_state = "review"
            charge.reconciliation_required = True
            await db.commit()
            raise AsaasFlowDenied("Referência ausente ou duplicada na Asaas: revisão manual obrigatória.")
        charge.asaas_payment_id = gateway.verify_payment_response(matches[0], charge)
    remote = await gateway.request("GET", "/payments/" + charge.asaas_payment_id)
    gateway.verify_payment_response(remote, charge)
    status = str(remote.get("status", "UNKNOWN")).upper()[:28]
    charge.provider_payment_status = status
    charge.payment_received_verified = status == "RECEIVED"
    charge.split_settled_verified = False
    charge.provider_split_status = "UNKNOWN"
    found_splits = await gateway.request("GET", "/payments/splits/paid", params={
        "paymentId": charge.asaas_payment_id, "limit": 20,
    })
    splits = found_splits.get("data")
    if not isinstance(splits, list) or len(splits) != 1:
        charge.reconciliation_required = True
        charge.provider_split_status = "MISMATCH"
    else:
        split = splits[0]
        if not isinstance(split, dict):
            raise AsaasFlowDenied("Split Asaas retornou dados inválidos.")
        sid = split.get("id")
        if not isinstance(sid, str) or len(sid) > 80:
            raise AsaasFlowDenied("Identificador de Split inválido.")
        charge.provider_split_id = sid
        if split.get("walletId") != charge.destination_wallet_id:
            charge.reconciliation_required = True
            charge.provider_split_status = "MISMATCH"
        else:
            charge.provider_split_status = str(split.get("status", "UNKNOWN"))[:28]
            charge.split_settled_verified = (
                charge.payment_received_verified
                and gateway.verify_split_response(split, charge, sid)
            )
    charge.creation_state = "created"
    charge.reconciliation_required = not charge.split_settled_verified
    charge.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return present(charge)


async def issue_payment_instructions(db: AsyncSession, *, tenant_id: str,
                                     student_id: str, charge_id: str) -> dict:
    charge = await get_charge(db, tenant_id, charge_id)
    if charge.student_id != student_id or charge.creation_state != "created":
        raise AsaasFlowDenied("Instruções indisponíveis para este aluno.")
    if charge.environment != gateway.environment():
        raise AsaasFlowDenied("Ambiente de cobrança divergente.")
    return await gateway.payment_instructions(charge.asaas_payment_id, charge.method)


async def verify_destination(db: AsyncSession, *, tenant_id: str,
                             reviewer_id: str, evidence_reference: str) -> dict:
    config = get_settings()
    if not config.asaas_wallet_review_enabled:
        raise AsaasFlowDenied("Homologação operacional da carteira desabilitada.")
    if not isinstance(evidence_reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", evidence_reference):
        raise AsaasFlowDenied("Referência de comprovante Asaas inválida.")
    await bind_tenant(db, tenant_id)
    target = (await db.execute(select(AsaasWorkspaceDestination).where(
        AsaasWorkspaceDestination.tenant_id == tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if target is None or target.status == "rejected" or target.confirmed_by_user_id == reviewer_id:
        raise AsaasFlowDenied("Destino sem comprovação ou revisão independente.")
    if target.status == "verified":
        raise AsaasFlowDenied("Destino já homologado.")
    # This action must be used ONLY after an out-of-band Asaas support/ownership check.
    target.status = "verified"
    target.verified_at = datetime.now(timezone.utc)
    target.verified_by_user_id = reviewer_id
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"verified": True, "wallet_id": target.wallet_id,
            "verification_reference": evidence_reference,
            "real_payments_enabled": False}
