"""initial schema baseline

Revision ID: 001_initial
Revises:
Create Date: 2026-10-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SELECT 1")
    op.execute("""
    DO $$ BEGIN
      ALTER TABLE tenants ADD COLUMN IF NOT EXISTS api_key_hash VARCHAR(128);
      ALTER TABLE tenants ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(128);
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END $$;
    """)
    op.execute("""
    DO $$ BEGIN
      CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_api_key_hash ON tenants (api_key_hash);
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenants_api_key_hash")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS webhook_secret")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS api_key_hash")
