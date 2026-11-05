"""smart import + custom fields (registry + JSONB)

Revision ID: 054_smart_import_custom_fields
Revises: 053_merge_heads

Cria `custom_field_definitions` (registry de campos customizados por tenant) e
adiciona `students.custom_fields` (JSONB com índice GIN) — adaptação de schema
em runtime sem DDL por coluna, como documentado em docs/SMART_IMPORT.md.

IMPORTANTE: este repositório possui arquivos de migração com numeração duplicada
(007, 036, 052). Antes de gerar, confira a cabeça real com `alembic heads` e,
se necessário, ajuste `down_revision`/`revises` abaixo para a cabeça corrente.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "054_smart_import_custom_fields"
down_revision = "053_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.String(length=50), nullable=False, server_default="student"),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_pii", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "target", "name", name="uq_custom_fields_tenant_target_name"),
    )
    op.create_index("ix_custom_fields_tenant_target", "custom_field_definitions",
                    ["tenant_id", "target", "active"])

    op.execute("ALTER TABLE custom_field_definitions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE custom_field_definitions FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY custom_field_definitions_tenant_isolation
        ON custom_field_definitions
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    op.add_column("students", sa.Column(
        "custom_fields", postgresql.JSONB(astext_type=sa.Text()),
        nullable=False, server_default=sa.text("'{}'::jsonb"),
    ))
    op.create_index(
        "ix_students_custom_fields_gin", "students", ["custom_fields"],
        postgresql_using="gin",
            )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS custom_field_definitions_tenant_isolation ON custom_field_definitions")
    op.drop_index("ix_students_custom_fields_gin", table_name="students")
    op.drop_column("students", "custom_fields")
    op.drop_index("ix_custom_fields_tenant_target", table_name="custom_field_definitions")
    op.drop_table("custom_field_definitions")
