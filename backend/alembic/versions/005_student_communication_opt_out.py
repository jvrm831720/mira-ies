"""Add student communication opt-out fields.

Revision ID: 005_student_opt_out
Revises: 004_mira_auth
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005_student_opt_out"
down_revision: Union[str, None] = "004_mira_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS communication_opt_out BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS communication_opted_out_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE students DROP COLUMN IF EXISTS communication_opted_out_at")
    op.execute("ALTER TABLE students DROP COLUMN IF EXISTS communication_opt_out")
