"""Wave 4D-A: payment preparation and sandbox-only HMAC evidence.

No PSP tool execution, no Pix/boletos issuance, no settlement assertions.
Workspace-specific Composio accounts are referenced, not copied or called.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.composio_connection import TenantComposioAccount
from app.models.finance_reconciliation import FinanceSourceProfile, FinanceObservation
from app.models.student import Student
from app.models.student_payments import AsaasWorkspaceDestination, PaymentProviderProfile, StudentPaymentIntent, StudentPaymentEvidence
from app.services.composio.categories import FINANCE_TOOLKITS
from app.services.dispatch_core import bind_tenant
from app.services.student_finance_composio import parse_amount, parse_datetime

PROVIDER_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
EVENT_STATES = frozenset({
    "created", "processing", "partially_paid_reported", "paid_reported",
    "failed", "refunded_reported", "chargeback_reported",
})
METHODS = frozenset({"pix", "boleto"})


class PaymentDenied(ValueError):
    """Business-level denial without provider secrets or payload disclosure."""


def enabled(*, event_ingress: bool = False) -> None:
    config = get_settings()
    if not (config.native_academic_enabled and config.native_academic_services_enabled
            and config.student_finance_reconciliation_enabled and config.student_payments_sandbox_enabled):
        raise PaymentDenied("Pagamentos em sandbox não habilitados.")
    if event_ingress and not config.student_payments_sandbox_webhooks_enabled:
        raise PaymentDenied("Eventos de sandbox não habilitados.")


def validate_provider(name: str, kind: str, provider_slug: str, methods: list[str]) -> None:
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 100:
        raise PaymentDenied("Nome do provedor inválido.")
    if kind not in {"composio", "custom_pending"}:
        raise PaymentDenied("O provedor deve usar uma conexão Composio ou estar aguardando homologação.")
    if not isinstance(provider_slug, str) or not PROVIDER_SLUG.fullmatch(provider_slug):
        raise PaymentDenied("Identificador de provedor inválido.")
    if not isinstance(methods, list) or not 1 <= len(methods) <= 2:
        raise PaymentDenied("Escolha Pix ou boleto, sem duplicações.")
    if any(not isinstance(v, str) or v not in METHODS for v in methods) or len(set(methods)) != len(methods):
        raise PaymentDenied("Somente métodos previamente permitidos são aceitos.")


async def validate_connection(db: AsyncSession, tenant_id: str, source: FinanceSourceProfile,
                              kind: str, provider_slug: str) -> str | None:
    if kind == "custom_pending":
        return None
    if (source.source_kind != "composio" or not source.enabled
            or not source.connected_account_id):
        raise PaymentDenied("A origem deve ser uma conexão Composio ativa e homologada para leitura.")
    account = (await db.execute(select(TenantComposioAccount).where(
        TenantComposioAccount.tenant_id == tenant_id,
        TenantComposioAccount.connected_account_id == source.connected_account_id,
        TenantComposioAccount.status == "active",
        TenantComposioAccount.disconnected_at.is_(None),
    ))).scalar_one_or_none()
    if (account is None or account.toolkit_slug not in FINANCE_TOOLKITS
            or account.toolkit_slug != provider_slug):
        raise PaymentDenied("Conta financeira Composio não disponível neste workspace.")
    return source.connected_account_id


async def create_provider(db: AsyncSession, *, tenant_id: str, user_id: str,
                          source_id: str, name: str, kind: str, slug: str,
                          methods: list[str]) -> PaymentProviderProfile:
    enabled()
    validate_provider(name, kind, slug, methods)
    await bind_tenant(db, tenant_id)
    source = (await db.execute(select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == tenant_id, FinanceSourceProfile.id == source_id,
    ))).scalar_one_or_none()
    if source is None:
        raise PaymentDenied("Origem financeira não pertence ao workspace.")
    linked = await validate_connection(db, tenant_id, source, kind, slug)
    result = PaymentProviderProfile(
        tenant_id=tenant_id, finance_profile_id=source.id, name=name.strip(),
        connection_kind=kind, connected_account_id=linked, provider_slug=slug,
        methods=list(methods), environment="sandbox", enabled=False,
        revision=1, created_by=user_id,
    )
    db.add(result)
    await db.commit()
    return result


async def change_provider_enabled(db: AsyncSession, *, tenant_id: str, provider_id: str,
                                  expected_revision: int, value: bool) -> PaymentProviderProfile:
    enabled()
    await bind_tenant(db, tenant_id)
    item = (await db.execute(select(PaymentProviderProfile).where(
        PaymentProviderProfile.tenant_id == tenant_id, PaymentProviderProfile.id == provider_id,
    ).with_for_update())).scalar_one_or_none()
    if item is None:
        raise PaymentDenied("Provedor não encontrado.")
    if item.revision != expected_revision:
        raise PaymentDenied("Configuração alterada por outro operador.")
    if value:
        if item.connection_kind != "composio":
            raise PaymentDenied("Integrações customizadas não podem ser ativadas sem homologação.")
        source = (await db.execute(select(FinanceSourceProfile).where(
            FinanceSourceProfile.tenant_id == tenant_id,
            FinanceSourceProfile.id == item.finance_profile_id,
        ))).scalar_one_or_none()
        if source is None or await validate_connection(
            db, tenant_id, source, item.connection_kind, item.provider_slug,
        ) != item.connected_account_id:
            raise PaymentDenied("A conexão financeira não está mais autorizada.")
    item.enabled = bool(value)
    item.revision += 1
    await db.commit()
    return item


def draft_amount(observation: FinanceObservation) -> Decimal:
    if observation.currency != "BRL" or observation.canonical_state not in {
        "open", "overdue", "partially_paid",
    }:
        raise PaymentDenied("Somente obrigações abertas, vencidas ou parciais admitem rascunho.")
    amount = Decimal(observation.amount) - Decimal(observation.paid_amount)
    if amount <= 0:
        raise PaymentDenied("Obrigação sem saldo a pagar.")
    return amount


def _request_hash(provider_id: str, observation_id: str, method: str) -> str:
    payload = json.dumps(
        {"provider": provider_id, "observation": observation_id, "method": method},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


async def create_draft(db: AsyncSession, *, tenant_id: str, user_id: str, provider_id: str,
                       observation_id: str, method: str, idempotency_key: str) -> dict:
    enabled()
    if method not in METHODS or not 16 <= len(idempotency_key) <= 120:
        raise PaymentDenied("Método ou chave idempotente inválida.")
    await bind_tenant(db, tenant_id)
    provider = (await db.execute(select(PaymentProviderProfile).where(
        PaymentProviderProfile.tenant_id == tenant_id,
        PaymentProviderProfile.id == provider_id,
    ).with_for_update())).scalar_one_or_none()
    if provider is None or provider.environment != "sandbox" or not provider.enabled:
        raise PaymentDenied("Provedor de sandbox não habilitado.")
    if method not in provider.methods:
        raise PaymentDenied("Método não permitido para este provedor.")
    if provider.connection_kind == "composio":
        source = (await db.execute(select(FinanceSourceProfile).where(
            FinanceSourceProfile.tenant_id == tenant_id,
            FinanceSourceProfile.id == provider.finance_profile_id,
        ))).scalar_one_or_none()
        if source is None or await validate_connection(
            db, tenant_id, source, provider.connection_kind, provider.provider_slug,
        ) != provider.connected_account_id:
            raise PaymentDenied("Conexão Composio foi revogada ou desativada.")
    destination = await get_destination(db, tenant_id)
    if destination is None:
        raise PaymentDenied("Cadastre a carteira Asaas de destino deste workspace.")
    request_hash = hashlib.sha256((_request_hash(provider_id, observation_id, method)
                                   + ":" + destination.wallet_id).encode()).hexdigest()
    old = (await db.execute(select(StudentPaymentIntent).where(
        StudentPaymentIntent.tenant_id == tenant_id,
        StudentPaymentIntent.provider_id == provider_id,
        StudentPaymentIntent.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if old:
        if old.request_hash != request_hash:
            raise PaymentDenied("Chave idempotente reutilizada para outra obrigação.")
        return describe_draft(old, deduplicated=True)
    obs = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant_id, FinanceObservation.id == observation_id,
        FinanceObservation.profile_id == provider.finance_profile_id,
    ))).scalar_one_or_none()
    if obs is None:
        raise PaymentDenied("Obrigação financeira inexistente para esta origem.")
    latest = (await db.execute(select(FinanceObservation.id).where(
        FinanceObservation.tenant_id == tenant_id,
        FinanceObservation.profile_id == obs.profile_id,
        FinanceObservation.external_id == obs.external_id,
    ).order_by(FinanceObservation.observed_at.desc(), FinanceObservation.id.desc()).limit(1))).scalar_one()
    if latest != obs.id:
        raise PaymentDenied("Observação não é a versão mais recente da obrigação.")
    student = (await db.execute(select(Student.id).where(
        Student.tenant_id == tenant_id, Student.id == obs.student_id,
        Student.is_active.is_(True),
    ))).scalar_one_or_none()
    if student is None:
        raise PaymentDenied("Aluno não está ativo neste workspace.")
    amount = draft_amount(obs)
    result = StudentPaymentIntent(
        tenant_id=tenant_id, provider_id=provider.id, financial_observation_id=obs.id,
        destination_wallet_id=destination.wallet_id,
        student_id=obs.student_id, method=method, amount=amount, currency="BRL",
        idempotency_key=idempotency_key, request_hash=request_hash,
        status="draft", created_by=user_id,
    )
    db.add(result)
    await db.commit()
    return describe_draft(result, deduplicated=False)


def describe_draft(item: StudentPaymentIntent, *, deduplicated: bool = False) -> dict:
    return {
        "id": item.id, "provider_id": item.provider_id,
        "financial_observation_id": item.financial_observation_id,
        "destination_wallet_id": item.destination_wallet_id,
        "student_id": item.student_id, "method": item.method,
        "amount": str(item.amount), "currency": item.currency,
        "status": "draft", "environment": "sandbox",
        "payment_link": None, "pix_code": None, "boleto": None,
        "settlement_confirmed": False, "deduplicated": deduplicated,
    }


def sandbox_secret() -> bytes:
    config = get_settings()
    secret = config.student_payments_sandbox_hmac_secret or ""
    if len(secret.encode()) < 32:
        raise PaymentDenied("Segredo de homologação indisponível.")
    return secret.encode()


def signed_sandbox_event(raw: bytes, timestamp: str, signature: str,
                         tenant_id: str, provider_id: str, *,
                         clock: datetime | None = None) -> None:
    enabled(event_ingress=True)
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 16384:
        raise PaymentDenied("Evento inválido ou acima do limite.")
    if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{10,11}", timestamp):
        raise PaymentDenied("Timestamp inválido.")
    try:
        stamp = int(timestamp)
        tenant_id, provider_id = str(UUID(tenant_id)), str(UUID(provider_id))
    except (ValueError, TypeError) as exc:
        raise PaymentDenied("Identificadores inválidos.") from exc
    when = clock or datetime.now(timezone.utc)
    if abs(when.timestamp() - stamp) > 300:
        raise PaymentDenied("Timestamp fora da janela de cinco minutos.")
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        raise PaymentDenied("Assinatura ausente ou malformada.")
    secret = sandbox_secret()
    per_provider = hmac.new(secret, f"mira:sandbox:{tenant_id}:{provider_id}".encode(), hashlib.sha256).digest()
    signed = b"v1:" + timestamp.encode() + b":" + raw
    expected = hmac.new(per_provider, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature[7:], expected):
        raise PaymentDenied("Assinatura inválida.")


def normalize_event(raw: bytes) -> dict:
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PaymentDenied("Evento JSON inválido.") from exc
    fields = {"event_id", "intent_id", "account_id", "state", "amount", "currency", "occurred_at"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise PaymentDenied("Envelope do evento não corresponde ao contrato.")
    for key in ("event_id", "account_id"):
        if not isinstance(payload[key], str) or not 1 <= len(payload[key]) <= 120:
            raise PaymentDenied("Identificador de evento inválido.")
    try:
        payload["intent_id"] = str(UUID(payload["intent_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PaymentDenied("Referência de rascunho inválida.") from exc
    if (not isinstance(payload["state"], str) or payload["state"] not in EVENT_STATES
            or payload["currency"] != "BRL"):
        raise PaymentDenied("Estado ou moeda do evento inválido.")
    try:
        payload["amount"] = parse_amount(payload["amount"])
        payload["occurred_at"] = parse_datetime(payload["occurred_at"])
    except (ValueError, TypeError) as exc:
        raise PaymentDenied("Valor ou data inválidos.") from exc
    if payload["occurred_at"] is None:
        raise PaymentDenied("Momento do evento obrigatório.")
    return payload


async def store_sandbox_event(db: AsyncSession, *, tenant_id: str, provider_id: str,
                              raw: bytes, timestamp: str, signature: str) -> dict:
    # Verify the signed envelope BEFORE accepting tenant context from the URL.
    signed_sandbox_event(raw, timestamp, signature, tenant_id, provider_id)
    payload = normalize_event(raw)
    digest = hashlib.sha256(raw).hexdigest()
    await bind_tenant(db, tenant_id)
    provider = (await db.execute(select(PaymentProviderProfile).where(
        PaymentProviderProfile.tenant_id == tenant_id, PaymentProviderProfile.id == provider_id,
        PaymentProviderProfile.environment == "sandbox",
        PaymentProviderProfile.enabled.is_(True),
    ).with_for_update())).scalar_one_or_none()
    if provider is None or provider.connection_kind != "composio":
        raise PaymentDenied("O provedor de sandbox está desabilitado.")
    if payload["account_id"] != provider.connected_account_id:
        raise PaymentDenied("Evento vinculado a outra conexão.")
    source = (await db.execute(select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == tenant_id,
        FinanceSourceProfile.id == provider.finance_profile_id,
    ))).scalar_one_or_none()
    if source is None or await validate_connection(
        db, tenant_id, source, provider.connection_kind, provider.provider_slug,
    ) != provider.connected_account_id:
        raise PaymentDenied("Conexão Composio revogada ou desabilitada.")
    old = (await db.execute(select(StudentPaymentEvidence).where(
        StudentPaymentEvidence.tenant_id == tenant_id,
        StudentPaymentEvidence.provider_id == provider_id,
        StudentPaymentEvidence.provider_event_id == payload["event_id"],
    ))).scalar_one_or_none()
    if old:
        if old.payload_hash != digest:
            raise PaymentDenied("ID de evento reutilizado com conteúdo diferente.")
        return {"accepted": True, "deduplicated": True, "settlement_confirmed": False}
    intent = (await db.execute(select(StudentPaymentIntent).where(
        StudentPaymentIntent.tenant_id == tenant_id,
        StudentPaymentIntent.provider_id == provider_id,
        StudentPaymentIntent.id == payload["intent_id"],
    ))).scalar_one_or_none()
    if intent is None:
        raise PaymentDenied("Rascunho de outro provedor ou workspace.")
    if payload["amount"] > intent.amount:
        raise PaymentDenied("Valor relatado excede o rascunho.")
    if payload["state"] == "paid_reported" and payload["amount"] != intent.amount:
        raise PaymentDenied("Pagamento integral relatado deve ter o valor completo.")
    if payload["state"] == "partially_paid_reported" and not (0 < payload["amount"] < intent.amount):
        raise PaymentDenied("Parcial relatada deve ser positiva e menor que o saldo.")
    db.add(StudentPaymentEvidence(
        tenant_id=tenant_id, provider_id=provider_id, intent_id=intent.id,
        provider_event_id=payload["event_id"],
        reported_state=payload["state"], reported_amount=payload["amount"],
        currency="BRL", payload_hash=digest, signature_type="mira_hmac_sandbox_v1",
        occurred_at=payload["occurred_at"],
    ))
    await db.commit()
    # A signed sandbox event is not a PSP-native confirmation of bank settlement.
    return {"accepted": True, "deduplicated": False, "settlement_confirmed": False}


def asaas_split_rule(wallet_id: str) -> dict:
    """Every workspace charge routes 100% of netValue to the same Asaas wallet.

    This is only the provider request fragment. Never accept split rules,
    recipient accounts or amounts from the student browser.
    """
    try:
        wallet_id = str(UUID(wallet_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PaymentDenied("A conta de destino precisa do walletId Asaas.") from exc
    return {"split": [{"walletId": wallet_id, "percentualValue": 100}]}


def destination_json(row: AsaasWorkspaceDestination | None) -> dict:
    if row is None:
        return {"configured": False, "status": "missing", "wallet_id": None,
                "version": None, "receives_percent_of_net": 100,
                "verified_for_live": False}
    return {"configured": True, "status": row.status, "wallet_id": row.wallet_id,
            "version": row.version, "receives_percent_of_net": 100,
            "verified_for_live": row.status == "verified"}


async def get_destination(db: AsyncSession, tenant_id: str, *, lock: bool = False):
    await bind_tenant(db, tenant_id)
    query = select(AsaasWorkspaceDestination).where(AsaasWorkspaceDestination.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def save_destination(db: AsyncSession, *, tenant_id: str, user_id: str,
                           wallet_id: str, expected_version: int | None,
                           confirms_ownership: bool) -> dict:
    enabled()
    if not confirms_ownership:
        raise PaymentDenied("Confirme que a carteira informada pertence à instituição.")
    try:
        normalized = str(UUID(wallet_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PaymentDenied("Informe o walletId da conta Asaas, não dados bancários.") from exc
    issuer = get_settings().student_payments_asaas_issuer_wallet_id
    if issuer:
        try:
            issuer_wallet = str(UUID(issuer))
        except ValueError as exc:
            raise PaymentDenied("Carteira Asaas emissora não configurada corretamente.") from exc
        if normalized == issuer_wallet:
            raise PaymentDenied("A conta emissora não pode receber o próprio Split.")
    await bind_tenant(db, tenant_id)
    # A transaction-scoped tenant lock prevents two concurrent first-time inserts.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                     {"key": f"asaas-destination:{tenant_id}"})
    current = await get_destination(db, tenant_id, lock=True)
    if current is None:
        if expected_version is not None:
            raise PaymentDenied("Versão inválida para um primeiro cadastro.")
        current = AsaasWorkspaceDestination(
            tenant_id=tenant_id, wallet_id=normalized,
            confirmed_by_user_id=user_id, status="pending", version=1,
        )
        db.add(current)
    else:
        if expected_version != current.version:
            raise PaymentDenied("Destinatário atualizado por outro operador.")
        if current.wallet_id != normalized:
            current.wallet_id = normalized
            current.status = "pending"
            current.verified_at = None
            current.verified_environment = None
            current.verified_by_user_id = None
        current.version += 1
        current.confirmed_by_user_id = user_id
        current.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return destination_json(current)


async def preview_asaas_split(db: AsyncSession, *, tenant_id: str,
                              observation_id: str) -> dict:
    """No API calls to Asaas; preview is not a payment or collection."""
    enabled()
    await bind_tenant(db, tenant_id)
    destination = await get_destination(db, tenant_id)
    if destination is None:
        raise PaymentDenied("Cadastre a carteira Asaas da IES antes de preparar pagamentos.")
    observation = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant_id, FinanceObservation.id == observation_id,
    ))).scalar_one_or_none()
    if observation is None:
        raise PaymentDenied("Obrigação não encontrada neste workspace.")
    latest = (await db.execute(select(FinanceObservation.id).where(
        FinanceObservation.tenant_id == tenant_id,
        FinanceObservation.profile_id == observation.profile_id,
        FinanceObservation.external_id == observation.external_id,
    ).order_by(FinanceObservation.observed_at.desc(), FinanceObservation.id.desc()).limit(1))).scalar_one()
    if latest != observation.id:
        raise PaymentDenied("Prévia requer a observação financeira mais recente.")
    amount = draft_amount(observation)
    return {
        "observation_id": observation.id, "student_id": observation.student_id,
        "source_profile_id": observation.profile_id,
        "method_options": ["PIX", "BOLETO"], "gross_charge_value": str(amount),
        "currency": "BRL", "split": asaas_split_rule(destination.wallet_id)["split"],
        "split_basis": "netValue", "receives_percent_of_net": 100,
        "recipient_verification": destination.status,
        "ready_for_real_charges": False, "charge_created": False,
        "payment_link": None, "pix_code": None, "boleto": None,
        "settlement_confirmed": False,
    }
