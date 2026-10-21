"""store outcome observation date and target definition

Revision ID: 003_outcome_target
Revises: 002_agents
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_outcome_target"
down_revision: Union[str, None] = "002_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Não mascarar schema incompleto: Alembic deve falhar, não marcar a revisão como aplicada.
    op.execute("ALTER TABLE training_events ADD COLUMN IF NOT EXISTS outcome_at TIMESTAMPTZ")
    op.execute("ALTER TABLE training_events ADD COLUMN IF NOT EXISTS target_definition VARCHAR(40)")


def downgrade() -> None:
    op.execute("ALTER TABLE training_events DROP COLUMN IF EXISTS target_definition")
    op.execute("ALTER TABLE training_events DROP COLUMN IF EXISTS outcome_at")
