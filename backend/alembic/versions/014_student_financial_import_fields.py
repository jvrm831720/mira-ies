"""Structured financial fields for imported students.

Revision ID: 014_student_financial
Revises: 013_control_center_billing
"""
from alembic import op
import sqlalchemy as sa

revision = "014_student_financial"
down_revision = "013_control_center_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("saldo_devedor", sa.Float(), nullable=True))
    op.add_column("students", sa.Column("status_financeiro", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "status_financeiro")
    op.drop_column("students", "saldo_devedor")
