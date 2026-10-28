"""Distinguish final scores from legacy adjusted scores and backfill real events.

Revision ID: 020_risk_assessment_score_basis
Revises: 019_risk_assessment_history
"""
from alembic import op
import sqlalchemy as sa

revision = "020_risk_assessment_score_basis"
down_revision = "019_risk_assessment_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_assessments", sa.Column("score_basis", sa.String(length=32), nullable=True))

    # risk_assessments has FORCE RLS; disable it only within this migration transaction
    # so schema backfill can run for all tenants. RLS is restored before commit.
    op.execute("ALTER TABLE risk_assessments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_assessments DISABLE ROW LEVEL SECURITY")

    op.execute("""
        UPDATE risk_assessments
        SET score_basis = 'final'
        WHERE score_basis IS NULL
    """)

    # Reuse only real historical TrainingEvents with a still-existing student from the
    # same tenant. Their adjusted_score predates the dynamic engagement adjustment,
    # so they receive a separate semantics version and are never compared to final scores.
    op.execute("""
        INSERT INTO risk_assessments (
            id, tenant_id, student_id, batch_id, scoring_run_id, evaluated_at,
            score, risk_level, model_version, score_semantics_version, model_scope,
            model_score, dynamic_adjustment, features_snapshot, explanation, context,
            created_at, score_basis
        )
        SELECT
            gen_random_uuid(), e.tenant_id, e.student_id, e.batch_id, e.id, e.scored_at,
            e.adjusted_score, e.risk_level, e.model_version, 'legacy-adjusted-v1',
            COALESCE(e.model_scope, 'base'), e.model_score, 0,
            COALESCE(e.features_snapshot, '{}'::jsonb),
            jsonb_build_object(
                'available', false,
                'reason', 'legacy_training_event_without_preserved_explanation'
            ),
            jsonb_build_object(
                'source', 'training_events',
                'legacy_semantics', 'adjusted_score before dynamic engagement adjustment',
                'source_event_id', e.id
            ),
            COALESCE(e.created_at, e.scored_at), 'legacy_adjusted'
        FROM training_events e
        JOIN students s ON s.id = e.student_id AND s.tenant_id = e.tenant_id
        WHERE e.student_id IS NOT NULL
          AND e.adjusted_score IS NOT NULL
          AND e.adjusted_score >= 0 AND e.adjusted_score <= 100
          AND e.risk_level IN ('baixo', 'medio', 'critico')
          AND NOT EXISTS (
              SELECT 1
              FROM risk_assessments existing
              WHERE existing.tenant_id = e.tenant_id
                AND existing.student_id = e.student_id
                AND existing.batch_id IS NOT DISTINCT FROM e.batch_id
                AND existing.model_version IS NOT DISTINCT FROM e.model_version
                AND existing.model_scope = COALESCE(e.model_scope, 'base')
                AND existing.context->>'source' = 'score_batch'
                AND abs(extract(epoch FROM (existing.created_at - e.created_at))) <= 5
          )
        ON CONFLICT (scoring_run_id, student_id) DO NOTHING
    """)

    op.alter_column(
        "risk_assessments", "score_basis", existing_type=sa.String(length=32),
        nullable=False, server_default=sa.text("'final'"),
    )
    op.execute("ALTER TABLE risk_assessments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_assessments FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE risk_assessments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_assessments DISABLE ROW LEVEL SECURITY")
    op.execute("""
        DELETE FROM risk_assessments
        WHERE score_basis = 'legacy_adjusted'
          AND context->>'source' = 'training_events'
    """)
    op.execute("ALTER TABLE risk_assessments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE risk_assessments FORCE ROW LEVEL SECURITY")
    op.drop_column("risk_assessments", "score_basis")
