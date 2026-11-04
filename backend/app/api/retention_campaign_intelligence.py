"""Explainable campaign opportunity recommendations for an authenticated tenant."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.student_groups import _build_summary
from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.services.campaign_opportunities import build_campaign_opportunities
from app.student_groups.catalog import GROUP_CATALOG_VERSION

router = APIRouter(
    prefix="/agents/retention/campaigns/intelligence",
    tags=["Inteligência de Campanhas"],
)


@router.get("/opportunities")
async def list_campaign_opportunities(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    """Return explainable campaign briefs derived from the canonical seven groups.

    Reach is deliberately an upper bound. Contactability, consent, recent-contact
    suppression and intervention history must be checked during audience simulation.
    This endpoint never creates a campaign or sends a message.
    """
    summary = await _build_summary(
        db,
        tenant_id=auth.tenant_id,
        evaluated_at=datetime.now(timezone.utc),
    )
    opportunities = build_campaign_opportunities(summary)
    return {
        "tenant_id": auth.tenant_id,
        "generated_at": summary["evaluated_at"],
        "catalog_version": GROUP_CATALOG_VERSION,
        "recommendation_engine": "signals-and-rules-v1",
        "is_ai_generated_copy": False,
        "students_evaluated": summary["evaluated"],
        "total_active_students": summary["total_eligible"],
        "truncated": summary["truncated"],
        "opportunities_count": len(opportunities),
        "opportunities": opportunities,
        "notes": [
            "Recomendações explicáveis baseadas no catálogo oficial de grupos e sinais.",
            "Estimativa de alcance é limite superior, não previsão de entrega.",
            "A simulação detalhada deve validar contato, consentimento, preferências, histórico e deduplicação.",
            "O grupo Sem score gera ação de saneamento interno e não autoriza contato automático.",
            "Nenhuma campanha é criada, aprovada, agendada ou executada por este endpoint.",
        ],
    }
