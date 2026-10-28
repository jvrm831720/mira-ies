"""Shared router, schemas and serializers for retention agents."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.intervention import InterventionLog

router = APIRouter()

_VALID_CHANNELS = {"whatsapp", "email", "sms"}
_VALID_RISK_LEVELS = {"baixo", "medio", "critico"}
_VALID_STATUSES = {"planned", "sending", "sent", "dry_run", "unknown", "failed", "skipped"}
_VALID_OUTCOMES = {
    "responded",
    "no_response",
    "stayed",
    "dropped",
    "transferred",
    "unknown",
}


class RetentionRunRequest(BaseModel):
    batch_id: Optional[str] = None
    campaign_id: Optional[str] = Field(default=None, max_length=120)
    risk_levels: list[str] = Field(default_factory=lambda: ["critico"], max_length=3)
    limit: int = Field(default=50, ge=1, le=500)
    dry_run: Optional[bool] = None
    channels: Optional[list[str]] = Field(default=None, max_length=3)
    prefer_whatsapp_medio: bool = False
    student_ids: Optional[list[str]] = Field(default=None, max_length=500)
    optimize_send_time: bool = False


class OutcomeUpdateRequest(BaseModel):
    outcome: Literal[
        "responded", "no_response", "stayed", "dropped", "transferred", "unknown"
    ]
    note: Optional[str] = Field(default=None, max_length=240)
    source: Literal["manual", "import", "system"] = "manual"


def _serialize_log(log: InterventionLog) -> dict:
    return {
        "id": log.id,
        "student_id": log.student_id,
        "matricula": log.matricula,
        "channel": log.channel,
        "risk_level": log.risk_level,
        "risk_score": log.risk_score,
        "status": log.status,
        "skip_reason": log.skip_reason,
        "decision_reason": log.decision_reason,
        "decision_context": log.decision_context,
        "error": log.error,
        "provider": log.provider,
        "external_id": log.external_id,
        "correlation_id": log.correlation_id,
        "idempotency_key": log.idempotency_key,
        "job_id": log.job_id,
        "campaign_id": log.campaign_id,
        "delivery_status": log.delivery_status,
        "delivery_event_id": log.delivery_event_id,
        "delivery_updated_at": log.delivery_updated_at,
        "message_preview": log.message_preview,
        "outcome": log.outcome,
        "outcome_at": log.outcome_at,
        "outcome_source": log.outcome_source,
        "outcome_note": log.outcome_note,
        "created_at": log.created_at,
    }
