"""Topic-level preferences must block a retention campaign in the backend."""
from sqlalchemy import select

from app.agents.orchestrator import RetentionOrchestrator
from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch


async def test_retention_topic_disabled_blocks_all_channels(tenant, db_session):
    tenant_obj, _key = tenant
    batch = UploadBatch(
        filename="topic.csv",
        original_filename="topic.csv",
        status="processed",
        tenant_id=tenant_obj.id,
        total_rows=1,
        processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant_obj.id,
        matricula="TOPIC-1",
        nome="Aluno Sem Retenção",
        telefone="11988887777",
        email="aluno@example.edu.br",
        risk_level="critico",
        risk_score=90,
        communication_preferences={
            "channels": {"whatsapp": True, "email": True, "sms": True},
            "topics": {"academic": True, "retention": False, "promotional": False},
        },
    )
    db_session.add(student)
    await db_session.commit()

    result = await RetentionOrchestrator(db_session, tenant_id=tenant_obj.id).run(
        risk_levels=["critico"], dry_run=True
    )
    assert result["totals"]["skipped"] == 1
    log = (
        await db_session.execute(
            select(InterventionLog).where(InterventionLog.student_id == student.id)
        )
    ).scalar_one()
    assert log.status == "skipped"
    assert log.skip_reason == "communication_preference_blocked"
    assert log.decision_context["topic"] == "retention"
