"""Database session management — preparado para Supabase Cloud."""

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()
database_url = make_url(settings.database_url).update_query_dict(
    {"prepared_statement_cache_size": "0"}
)

engine = create_async_engine(
    database_url,
    echo=settings.debug,
    future=True,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    },
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def ensure_schema_patches(conn) -> None:
    """Additive schema patches for environments where create_all / alembic lag the ORM.

    Safe to run repeatedly (IF NOT EXISTS). Does not drop or rewrite data.
    Covers intervention_logs columns required by list_retention_logs serialization.
    """
    patches = [
        # Users / invites (legacy drift)
        """
        ALTER TABLE mira_users
        ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'coordinator'
        """,
        """
        ALTER TABLE mira_users
        ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE mira_users
        ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE mira_users
        ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ NULL
        """,
        """
        ALTER TABLE mira_org_invites
        ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'coordinator'
        """,
        # Intervention logs — decision / outcome (post-create_all)
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS decision_reason VARCHAR(240) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS decision_context JSONB NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS outcome VARCHAR(40) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS outcome_at TIMESTAMPTZ NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS outcome_source VARCHAR(40) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS outcome_note VARCHAR(240) NULL
        """,
        # Intervention logs — safe delivery (migration 006)
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(160) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS job_id VARCHAR(80) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS campaign_id VARCHAR(120) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(30) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS delivery_event_id VARCHAR(160) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS delivery_updated_at TIMESTAMPTZ NULL
        """,
        # Core columns that older partial tables might miss
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS template_id VARCHAR(80) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS message_preview VARCHAR(160) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS skip_reason VARCHAR(120) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS error TEXT NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS provider VARCHAR(40) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS external_id VARCHAR(120) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS risk_score FLOAT NULL
        """,
        """
        ALTER TABLE intervention_logs
        ADD COLUMN IF NOT EXISTS channel VARCHAR(20) NULL
        """,
        # Helpful indexes (idempotent)
        """
        CREATE INDEX IF NOT EXISTS ix_intervention_logs_correlation_id
        ON intervention_logs (correlation_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_intervention_logs_job_id
        ON intervention_logs (job_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_intervention_logs_campaign_id
        ON intervention_logs (campaign_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_intervention_logs_tenant_external_id
        ON intervention_logs (tenant_id, external_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_intervention_logs_tenant_outcome
        ON intervention_logs (tenant_id, outcome)
        """,
    ]
    for sql in patches:
        try:
            await conn.execute(text(sql))
        except Exception as exc:
            # Table may not exist yet; create_all / alembic will handle structure.
            print(f"Aviso schema patch: {type(exc).__name__}: {exc}")

    # Unique constraint for idempotency (nullable keys allowed multiple NULLs in PG)
    try:
        await conn.execute(
            text(
                """
                DO $$ BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_intervention_logs_tenant_idempotency_key'
                  ) THEN
                    ALTER TABLE intervention_logs
                      ADD CONSTRAINT uq_intervention_logs_tenant_idempotency_key
                      UNIQUE (tenant_id, idempotency_key);
                  END IF;
                END $$;
                """
            )
        )
    except Exception as exc:
        print(f"Aviso schema patch (idempotency constraint): {type(exc).__name__}: {exc}")


# Backwards-compatible alias used by older call sites / tests
_dev_schema_patches = ensure_schema_patches


async def init_db():
    from app.models import student, tenant, intervention  # noqa: F401
    from app.models import auth, control_center  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_schema_patches(conn)


async def apply_runtime_schema_patches() -> None:
    """Apply additive patches without create_all (production-safe)."""
    async with engine.begin() as conn:
        await ensure_schema_patches(conn)
