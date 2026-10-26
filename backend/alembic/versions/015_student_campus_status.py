"""Add academic campus and student status fields.

Revision ID: 015_student_campus_status
Revises: 014_student_financial_import_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "015_student_campus_status"
down_revision = "014_student_financial_import_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("campus", sa.String(length=150), nullable=True))
    op.add_column("students", sa.Column("status_aluno", sa.String(length=80), nullable=True))
    op.create_index("ix_students_campus", "students", ["campus"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_students_campus", table_name="students")
    op.drop_column("students", "status_aluno")
    op.drop_column("students", "campus")
