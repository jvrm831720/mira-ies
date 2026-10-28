"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator, preview_message, fetch_eligible_students
from app.agents.rules import decide_channels
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog, ProviderCallMetric
from app.models.student import Student
from app.models.engagement import StudentEngagementEvent
from app.services.consent import is_communication_allowed
from app.services.engagement import record_engagement_event, recommend_send_time
from app.services.retention_queue import enqueue_retention_job, get_job, redis_client

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


def _iso(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_log(log: InterventionLog) -> dict:
    """Stable contract for frontend: count/logs consumers."""
    return {
        "id": log.id,
        "student_id": log.student_id,
        "matricula": log.matricula,
        "channel": log.channel,
        "risk_level": log.risk_level,
        "risk_score": log.risk_score,
        "status": log.status,
        "skip_reason": log.skip_reason,
        "decision_reason": getattr(log, "decision_reason", None),
        "decision_context": getattr(log, "decision_context", None),
        "error": log.error,
        "provider": log.provider,
        "external_id": log.external_id,
        "correlation_id": getattr(log, "correlation_id", None),
        "idempotency_key": getattr(log, "idempotency_key", None),
        "job_id": getattr(log, "job_id", None),
        "campaign_id": getattr(log, "campaign_id", None),
        "delivery_status": getattr(log, "delivery_status", None),
        "delivery_event_id": getattr(log, "delivery_event_id", None),
        "delivery_updated_at": _iso(getattr(log, "delivery_updated_at", None)),
        "message_preview": log.message_preview,
        "outcome": getattr(log, "outcome", None),
        "outcome_at": _iso(getattr(log, "outcome_at", None)),
        "outcome_source": getattr(log, "outcome_source", None),
        "outcome_note": getattr(log, "outcome_note", None),
        "created_at": _iso(log.created_at),
    }
