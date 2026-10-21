"""Regressões para evitar duplicidade e fallback inseguro em envios reais."""

from sqlalchemy import func, select

from app.agents.base import SendResult
from app.agents.orchestrator import RetentionOrchestrator
from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch
from app.services.delivery_webhooks import normalize_delivery_event


async def _student(db_session, tenant):
    batch = UploadBatch(filename="x.csv", original_filename="x.csv", status="scored", tenant_id=tenant.id)
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant.id,
        matricula="SAFE-1",
        nome="Aluno Seguro",
        curso="Engenharia",
        risk_level="critico",
        risk_score=92.0,
        telefone="11988887777",
        email="aluno@example.com",
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


class _AmbiguousAgent:
    channel = "whatsapp"

    def render(self, _ctx):
        return "Mensagem"

    async def send(self, _ctx, _message, *, dry_run, idempotency_key=None):
        assert dry_run is False
        assert idempotency_key
        return SendResult(
            ok=False,
            channel="whatsapp",
            provider="evolution",
            error="timeout",
            outcome="unknown",
            ambiguous=True,
            halt_fallback=True,
        )


class _SuccessAgent:
    channel = "whatsapp"

    def render(self, _ctx):
        return "Mensagem"

    async def send(self, _ctx, _message, *, dry_run, idempotency_key=None):
        return SendResult(ok=True, channel="whatsapp", provider="dry_run", dry_run=True)


async def test_ambiguous_provider_result_does_not_fallback_to_email(tenant, db_session, monkeypatch):
    t, _raw_key = tenant
    await _student(db_session, t)
    from app.agents import orchestrator as orchestrator_module

    email_called = False

    class _EmailMustNotRun(_AmbiguousAgent):
        channel = "email"

        async def send(self, *_args, **_kwargs):
            nonlocal email_called
            email_called = True
            return SendResult(ok=True, channel="email", provider="dry_run", dry_run=True)

    monkeypatch.setitem(
        orchestrator_module.CHANNEL_AGENTS,
        "whatsapp",
        _AmbiguousAgent(),
    )
    monkeypatch.setitem(orchestrator_module.CHANNEL_AGENTS, "email", _EmailMustNotRun())

    result = await RetentionOrchestrator(db_session, tenant_id=t.id).run(
        risk_levels=["critico"], dry_run=False
    )

    assert result["totals"]["unknown"] == 1
    assert email_called is False
    log = (await db_session.execute(select(InterventionLog))).scalar_one()
    assert log.status == "unknown"
    assert log.delivery_status == "unknown"


async def test_same_idempotency_key_reuses_reserved_success(tenant, db_session, monkeypatch):
    t, _raw_key = tenant
    await _student(db_session, t)
    from app.agents import orchestrator as orchestrator_module

    monkeypatch.setitem(orchestrator_module.CHANNEL_AGENTS, "whatsapp", _SuccessAgent())
    orchestrator = RetentionOrchestrator(db_session, tenant_id=t.id)
    monkeypatch.setattr(orchestrator.settings, "agents_min_hours_between_contact", -1)
    monkeypatch.setattr(orchestrator.settings, "agents_max_contacts_per_week", 10)

    first = await orchestrator.run(
        risk_levels=["critico"],
        channels=["whatsapp"],
        dry_run=True,
        idempotency_key="same-run",
    )
    second = await orchestrator.run(
        risk_levels=["critico"],
        channels=["whatsapp"],
        dry_run=True,
        idempotency_key="same-run",
    )

    assert first["totals"]["dry_run"] == 1
    assert second["totals"]["dry_run"] == 1
    count = (await db_session.execute(select(func.count(InterventionLog.id)))).scalar()
    assert count == 1


def test_delivery_webhook_normalization_handles_provider_payloads():
    evolution = normalize_delivery_event(
        "evolution",
        {"event": "messages.upsert", "data": {"key": {"id": "wa-1"}, "status": "READ"}},
    )
    resend = normalize_delivery_event(
        "resend", {"type": "email.bounced", "data": {"email_id": "re-1"}}
    )
    twilio = normalize_delivery_event(
        "twilio", {"MessageSid": "SM-1", "MessageStatus": "delivered"}
    )
    twilio_read = normalize_delivery_event(
        "twilio", {"MessageSid": "SM-1", "MessageStatus": "read"}
    )
    opt_out = normalize_delivery_event(
        "twilio", {"MessageSid": "SM-2", "Body": "PARAR"}
    )

    assert evolution and evolution.status == "read" and evolution.external_id == "wa-1"
    assert resend and resend.status == "bounced" and resend.external_id == "re-1"
    assert twilio and twilio.status == "delivered" and twilio.external_id == "SM-1"
    assert twilio_read and twilio_read.status == "read" and twilio_read.event_id != twilio.event_id
    assert opt_out and opt_out.status == "opted_out" and opt_out.external_id == "SM-2"
