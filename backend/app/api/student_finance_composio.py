"""Institution-only Composio financial read path; never accepts student-facing tool calls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import _require_ies
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.financial_composio import StudentFinancialSyncRun
from app.services import student_finance_composio as finance
from app.services.composio.connections import ConnectionDenied
from app.services.composio.policy import ComposioPolicyDenied
from app.services.composio.client import ComposioSDKUnavailable

router = APIRouter(prefix="/native-academic/finance/composio", tags=["MIRA Education — Composio Finance"])


class ReadFinance(BaseModel):
    connected_account_id: str = Field(min_length=1, max_length=120)
    tool_slug: str = Field(min_length=1, max_length=120)
    arguments: dict = Field(default_factory=dict)
    rows_path: str = Field(default="", max_length=240)
    field_map: dict[str, str] = Field(min_length=6, max_length=7)


@router.post("/sync", status_code=201)
async def sync(
    body: ReadFinance,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Importação financeira exige sessão MFA AAL2.")
    await _require_ies(db, auth)
    try:
        return await finance.sync_financial(
            db, tenant_id=auth.tenant_id, actor_id=auth.user_id,
            account_id=body.connected_account_id, tool_slug=body.tool_slug,
            arguments=body.arguments, rows_path=body.rows_path,
            fields=body.field_map, idempotency_key=idempotency_key,
        )
    except (finance.FinancialReadDenied, ConnectionDenied, ComposioPolicyDenied,
            ComposioSDKUnavailable, ValueError, TypeError) as exc:
        await db.rollback()
        # No exception strings from providers are shown to the frontend.
        raise HTTPException(status_code=422, detail="A leitura financeira não passou na validação de conexão, política ou dados.") from exc


@router.get("/syncs")
async def syncs(
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    await _require_ies(db, auth)
    rows = (await db.execute(select(StudentFinancialSyncRun).where(
        StudentFinancialSyncRun.tenant_id == auth.tenant_id,
    ).order_by(StudentFinancialSyncRun.synced_at.desc()).limit(50))).scalars().all()
    return {"items": [{
        "id": row.id, "toolkit": row.toolkit, "tool_slug": row.tool_slug,
        "record_count": row.record_count, "synced_at": row.synced_at.isoformat(),
    } for row in rows]}
