"""Safe payment preparation built on Wave 4C provenance.

No PSP adapter, no Composio write tools, no webhook settlement, no checkout URL.
Even approved proposals cannot execute financial operations in Wave 4D-A.
"""
from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.finance_reconciliation import FinanceObservation, FinanceSourceProfile
from app.models.student import Student
from app.models.student_payments import StudentPaymentConnector, StudentPaymentOrder, StudentPaymentOrderEvent
from app.services.dispatch_core import bind_tenant

_ELIGIBLE = {"open", "overdue", "partially_paid"}
_TRANSITIONS = {
    "draft": {"awaiting_approval", "cancelled"},
    "awaiting_approval": {"approved", "cancelled"},
    "approved": {"cancelled"},
    "cancelled": set(),
}


class PaymentPreparationDenied(ValueError):
    """Tenant-safe validation; never includes raw provider data."""


def require_enabled() -> None:
    settings = get_settings()
    if not (settings.student_payment_preparation_enabled
            and settings.student_finance_reconciliation_enabled
            and settings.native_academic_enabled
            and settings.native_academic_services_enabled):
        raise PaymentPreparationDenied("Preparação de pagamentos ainda em homologação.")


def normalize_destination_wallet(wallet_id: str, issuer_wallet_id: str | None = None) -> str:
    """Asaas Split requires a wallet UUID from a receiving Asaas account.

    UUID format validation is NOT proof of recipient ownership / KYC.
    """
    try:
        wallet = UUID(str(wallet_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PaymentPreparationDenied("Informe um walletId Asaas válido.") from exc
    if wallet.int == 0:
        raise PaymentPreparationDenied("Carteira de destino inválida.")
    if issuer_wallet_id:
        try:
            issuer = UUID(str(issuer_wallet_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise PaymentPreparationDenied("Carteira da conta emissora não configurada corretamente.") from exc
        if wallet == issuer:
            raise PaymentPreparationDenied("A carteira emissora não pode receber seu próprio split.")
    return str(wallet)


def build_asaas_charge_split(wallet_id: str, *, issuer_wallet_id: str | None = None) -> dict:
    """Read-only split template for future POST /v3/payments; no network call."""
    recipient = normalize_destination_wallet(wallet_id, issuer_wallet_id)
    return {"split": [{"walletId": recipient, "percentualValue": 100}]}


def amount_for_observation(obs: FinanceObservation) -> Decimal:
    if obs.currency != "BRL" or obs.canonical_state not in _ELIGIBLE:
        raise PaymentPreparationDenied("Obrigação não elegível para proposta.")
    if obs.amount is None or obs.paid_amount is None:
        raise PaymentPreparationDenied("Obrigação sem valores confiáveis.")
    due = Decimal(str(obs.amount)) - Decimal(str(obs.paid_amount))
    if not due.is_finite() or due <= 0 or due > Decimal("9999999999.99"):
        raise PaymentPreparationDenied("Saldo não elegível para proposta.")
    if due.as_tuple().exponent < -2:
        raise PaymentPreparationDenied("Valor com mais de duas casas decimais.")
    return due.quantize(Decimal("0.01"))


async def create_connector(
    db: AsyncSession, *, tenant_id: str, actor_id: str,
    destination_wallet_id: str, finance_profile_id: str,
) -> StudentPaymentConnector:
    require_enabled()
    destination = normalize_destination_wallet(destination_wallet_id, getattr(get_settings(), "asaas_issuer_wallet_id", None))
    await bind_tenant(db, tenant_id)
    finance = (await db.execute(select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == tenant_id,
        FinanceSourceProfile.id == finance_profile_id,
    ))).scalar_one_or_none()
    if finance is None:
        raise PaymentPreparationDenied("Fonte financeira inexistente no workspace.")
    connector = StudentPaymentConnector(
        tenant_id=tenant_id,
        name="Asaas • " + finance.name[:55] + " • " + destination.split("-")[0],
        provider_slug="asaas",
        destination_wallet_id=destination, destination_verification_status="pending",
        finance_profile_id=finance_profile_id, mode="sandbox", enabled=False,
        created_by=actor_id, configuration_version=1,
    )
    db.add(connector)
    await db.commit()
    return connector


async def get_connector(
    db: AsyncSession, tenant_id: str, connector_id: str, *, lock: bool = False,
) -> StudentPaymentConnector:
    await bind_tenant(db, tenant_id)
    statement = select(StudentPaymentConnector).where(
        StudentPaymentConnector.tenant_id == tenant_id,
        StudentPaymentConnector.id == connector_id,
    )
    if lock:
        statement = statement.with_for_update()
    connector = (await db.execute(statement)).scalar_one_or_none()
    if connector is None:
        raise PaymentPreparationDenied("Conector não encontrado neste workspace.")
    return connector


async def toggle_connector(
    db: AsyncSession, *, tenant_id: str, connector_id: str,
    expected_version: int, enabled: bool,
) -> StudentPaymentConnector:
    require_enabled()
    connector = await get_connector(db, tenant_id, connector_id, lock=True)
    if connector.configuration_version != expected_version:
        raise PaymentPreparationDenied("Configuração alterada por outro operador.")
    finance = (await db.execute(select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == tenant_id,
        FinanceSourceProfile.id == connector.finance_profile_id,
        FinanceSourceProfile.enabled.is_(True),
    ))).scalar_one_or_none()
    if enabled and finance is None:
        raise PaymentPreparationDenied("Origem financeira precisa estar ativa.")
    if enabled and connector.destination_verification_status == "blocked":
        raise PaymentPreparationDenied("Carteira de destino bloqueada.")
    connector.enabled = enabled
    connector.configuration_version += 1
    connector.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return connector


async def _latest_observation(
    db: AsyncSession, tenant_id: str, observed: FinanceObservation,
) -> FinanceObservation:
    latest = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant_id,
        FinanceObservation.profile_id == observed.profile_id,
        FinanceObservation.external_id == observed.external_id,
    ).order_by(FinanceObservation.observed_at.desc(), FinanceObservation.id.desc()).limit(1))).scalar_one_or_none()
    if latest is None or latest.id != observed.id:
        raise PaymentPreparationDenied("Observação financeira ficou desatualizada.")
    return latest


def _is_idempotency_key(key: str) -> bool:
    return isinstance(key, str) and 16 <= len(key) <= 120 and key.isascii() and key.isprintable()


async def prepare_order(
    db: AsyncSession, *, tenant_id: str, connector_id: str,
    observation_id: str, actor_id: str, idempotency_key: str,
) -> tuple[StudentPaymentOrder, bool]:
    require_enabled()
    if not _is_idempotency_key(idempotency_key):
        raise PaymentPreparationDenied("Idempotency-Key inválida.")
    connector = await get_connector(db, tenant_id, connector_id, lock=True)
    if not connector.enabled or connector.mode != "sandbox" or connector.provider_slug != "asaas":
        raise PaymentPreparationDenied("Conector Asaas não habilitado em sandbox.")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:ref,0))"),
                     {"ref": f"pay:order:{tenant_id}:{connector_id}"})
    earlier = (await db.execute(select(StudentPaymentOrder).where(
        StudentPaymentOrder.tenant_id == tenant_id,
        StudentPaymentOrder.connector_id == connector_id,
        StudentPaymentOrder.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if earlier:
        if earlier.observation_id != observation_id:
            raise PaymentPreparationDenied("Chave idempotente reutilizada em outra obrigação.")
        return earlier, True
    observed = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant_id,
        FinanceObservation.id == observation_id,
        FinanceObservation.profile_id == connector.finance_profile_id,
    ))).scalar_one_or_none()
    if observed is None:
        raise PaymentPreparationDenied("Obrigação de outro perfil ou workspace.")
    await _latest_observation(db, tenant_id, observed)
    due = amount_for_observation(observed)
    finance = (await db.execute(select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == tenant_id,
        FinanceSourceProfile.id == connector.finance_profile_id,
        FinanceSourceProfile.enabled.is_(True),
    ))).scalar_one_or_none()
    if finance is None:
        raise PaymentPreparationDenied("Fonte financeira desabilitada.")
    student = (await db.execute(select(Student.id).where(
        Student.tenant_id == tenant_id, Student.id == observed.student_id,
        Student.is_active.is_(True),
    ))).scalar_one_or_none()
    if student is None:
        raise PaymentPreparationDenied("Aluno não está ativo no workspace.")
    already = (await db.execute(select(StudentPaymentOrder.id).where(
        StudentPaymentOrder.tenant_id == tenant_id,
        StudentPaymentOrder.connector_id == connector_id,
        StudentPaymentOrder.observation_id == observation_id,
    ))).scalar_one_or_none()
    if already is not None:
        raise PaymentPreparationDenied("Já há proposta para esta obrigação neste conector.")
    order = StudentPaymentOrder(
        tenant_id=tenant_id, connector_id=connector_id,
        observation_id=observed.id, student_id=observed.student_id,
        amount=due, currency="BRL",
        source_fingerprint=observed.fingerprint, status="draft",
        requested_by=actor_id, idempotency_key=idempotency_key,
    )
    db.add(order)
    await db.flush()
    db.add(StudentPaymentOrderEvent(
        tenant_id=tenant_id, order_id=order.id, actor_id=actor_id,
        status="draft", note="Proposta calculada a partir da observação financeira; sem pagamento.",
    ))
    await db.commit()
    return order, False


async def transition_order(
    db: AsyncSession, *, tenant_id: str, order_id: str,
    actor_id: str, target: str, note: str, expected_status: str,
) -> StudentPaymentOrder:
    require_enabled()
    await bind_tenant(db, tenant_id)
    if not isinstance(note, str) or not 5 <= len(note.strip()) <= 500:
        raise PaymentPreparationDenied("Justificativa entre 5 e 500 caracteres é obrigatória.")
    order = (await db.execute(select(StudentPaymentOrder).where(
        StudentPaymentOrder.tenant_id == tenant_id,
        StudentPaymentOrder.id == order_id,
    ).with_for_update())).scalar_one_or_none()
    if order is None:
        raise PaymentPreparationDenied("Proposta não encontrada neste workspace.")
    if order.status != expected_status or target not in _TRANSITIONS[order.status]:
        raise PaymentPreparationDenied("Transição inexistente ou proposta já alterada.")
    if target == "approved":
        if order.requested_by == actor_id:
            raise PaymentPreparationDenied("Solicitante não pode aprovar a própria proposta.")
        connector = await get_connector(db, tenant_id, order.connector_id)
        if not connector.enabled or connector.mode != "sandbox":
            raise PaymentPreparationDenied("Conector não está habilitado em sandbox.")
        observation = (await db.execute(select(FinanceObservation).where(
            FinanceObservation.tenant_id == tenant_id,
            FinanceObservation.id == order.observation_id,
            FinanceObservation.profile_id == connector.finance_profile_id,
        ))).scalar_one_or_none()
        if observation is None:
            raise PaymentPreparationDenied("Fonte da obrigação indisponível.")
        await _latest_observation(db, tenant_id, observation)
        if observation.fingerprint != order.source_fingerprint or amount_for_observation(observation) != order.amount:
            raise PaymentPreparationDenied("Valores ou estado alterados desde o preparo da proposta.")
        order.approved_by = actor_id
        order.approved_at = datetime.now(timezone.utc)
    order.status = target
    order.updated_at = datetime.now(timezone.utc)
    db.add(StudentPaymentOrderEvent(
        tenant_id=tenant_id, order_id=order.id,
        status=target, actor_id=actor_id, note=note.strip(),
    ))
    await db.commit()
    return order


def order_json(row: StudentPaymentOrder) -> dict:
    return {
        "id": row.id, "connector_id": row.connector_id,
        "observation_id": row.observation_id, "student_id": row.student_id,
        "amount": str(row.amount), "currency": "BRL", "status": row.status,
        "created_at": row.created_at.isoformat(),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "provider_execution_enabled": False, "settlement_confirmed": False,
        "checkout_url": None, "pix": None, "boleto": None,
    }
