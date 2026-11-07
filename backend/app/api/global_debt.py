"""Wave 2: explicit institutional debt disclosure and user consent.

Never join tenant finance tables in a global session. Staff snapshots only
records belonging to their own tenant; a separately verified global account
must opt in before any financial amount is disclosed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.global_student_auth import _action, _configured, _session
from app.api.native_academic import _require_ies
from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.finance_reconciliation import FinanceObservation
from app.models.global_debt import GlobalDebtGrant, GlobalDebtSnapshot
from app.models.global_student_identity import GlobalStudentAccount
from app.models.tenant import Tenant

router = APIRouter(prefix="/global-portal/debts", tags=["Portal MIRA — agregador"])
institution_router = APIRouter(prefix="/native-academic/global-debt", tags=["Portal MIRA — concessões"])


def _enabled():
    settings = get_settings()
    if not settings.global_student_debt_aggregation_enabled:
        raise HTTPException(503, "Agregação de pendências ainda em homologação.")
    _configured()


def _verified(account: GlobalStudentAccount):
    if account.identity_verified_at is None:
        raise HTTPException(403, "Comprovação independente de titularidade obrigatória.")


class GrantInput(BaseModel):
    account_id: UUID
    student_id: UUID
    observation_ids: list[UUID] = Field(min_length=1, max_length=100)
    evidence_reference: str = Field(min_length=12, max_length=120)
    # The institution must record a verifiable, reviewed evidence reference.
    # Account UUID is NOT proof of identity or enrollment.


async def _staff(auth: AuthContext, db: AsyncSession):
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(403, "É necessária sessão institucional MFA AAL2.")
    await _require_ies(db, auth)


@institution_router.post("/grants", status_code=201)
async def create_grant(body: GrantInput, auth: AuthContext = Depends(require_permission("settings.manage")),
                       db: AsyncSession = Depends(get_db)):
    _enabled()
    await _staff(auth, db)
    # Tenant RLS is already bound by require_permission/get_current_tenant.
    # Never query the global identity table from an institutional request.
    obs_ids = sorted({str(value) for value in body.observation_ids})
    observations = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == auth.tenant_id,
        FinanceObservation.student_id == str(body.student_id),
        FinanceObservation.id.in_(obs_ids),
    ))).scalars().all()
    if len(observations) != len(obs_ids):
        raise HTTPException(422, "Observações inválidas ou fora do workspace/aluno.")
    grant = (await db.execute(select(GlobalDebtGrant).where(
        GlobalDebtGrant.tenant_id == auth.tenant_id,
        GlobalDebtGrant.student_id == str(body.student_id),
        GlobalDebtGrant.account_id == str(body.account_id),
    ).with_for_update())).scalar_one_or_none()
    if grant is not None:
        raise HTTPException(409, "Associação existente. Revogue e solicite revisão.")
    grant = GlobalDebtGrant(
        tenant_id=auth.tenant_id, student_id=str(body.student_id),
        account_id=str(body.account_id), evidence_reference=body.evidence_reference,
        created_by=auth.user_id, state="pending",
    )
    db.add(grant)
    await db.flush()
    tenant = await db.get(Tenant, auth.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(422, "Instituição não disponível.")
    for obs in observations:
        db.add(GlobalDebtSnapshot(
            grant_id=grant.id, tenant_id=auth.tenant_id, observation_id=obs.id,
            label=obs.label, creditor_name=tenant.name, amount=obs.amount, paid_amount=obs.paid_amount,
            currency=obs.currency, state=obs.canonical_state,
            due_at=obs.due_at, observed_at=obs.observed_at,
        ))
    await db.commit()
    return {"grant_id": grant.id, "state": "pending", "observation_count": len(observations)}


@institution_router.post("/grants/{grant_id}/revoke")
async def revoke_grant(grant_id: UUID, auth: AuthContext = Depends(require_permission("settings.manage")),
                       db: AsyncSession = Depends(get_db)):
    _enabled()
    await _staff(auth, db)
    grant = (await db.execute(select(GlobalDebtGrant).where(
        GlobalDebtGrant.id == str(grant_id), GlobalDebtGrant.tenant_id == auth.tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if not grant:
        raise HTTPException(404, "Associação não encontrada.")
    grant.state = "revoked"
    grant.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"state": "revoked"}


@router.get("/consents")
async def pending_consents(request: Request, db: AsyncSession = Depends(get_db)):
    _enabled()
    _, account = await _session(request, db, _configured())
    _verified(account)
    rows = (await db.execute(select(GlobalDebtGrant).where(
        GlobalDebtGrant.account_id == account.id,
        GlobalDebtGrant.state == "pending",
    ).order_by(GlobalDebtGrant.created_at.desc()).limit(100))).scalars().all()
    # Creditor identity and the exact scope are mandatory for informed consent.
    counts = {}
    creditors = {}
    if rows:
        summaries = (await db.execute(select(
            GlobalDebtSnapshot.grant_id, func.count(GlobalDebtSnapshot.id),
            func.min(GlobalDebtSnapshot.creditor_name),
        ).where(GlobalDebtSnapshot.grant_id.in_([row.id for row in rows]))
         .group_by(GlobalDebtSnapshot.grant_id))).all()
        counts = {grant_id: count for grant_id, count, _ in summaries}
        creditors = {grant_id: name for grant_id, _, name in summaries}
    return {"items": [{
        "grant_id": row.id, "created_at": row.created_at.isoformat(),
        "creditor_name": creditors[row.id], "record_count": counts[row.id],
        "scope": "Exibição de registros financeiros históricos desta instituição",
    } for row in rows if row.id in creditors and counts.get(row.id, 0) > 0]}
