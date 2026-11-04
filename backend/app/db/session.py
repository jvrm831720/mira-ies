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


_INTERVENTION_LOG_REQUIRED_COLUMNS = frozenset({
    "id",
    "tenant_id",
    "student_id",
    "matricula",
    "channel",
    "risk_level",
    "risk_score",
    "template_id",
    "message_preview",
    "status",
    "skip_reason",
    "decision_reason",
    "decision_context",
    "error",
    "provider",
    "external_id",
    "correlation_id",
    "idempotency_key",
    "job_id",
    "campaign_id",
    "delivery_status",
    "delivery_event_id",
    "delivery_updated_at",
    "outcome",
    "outcome_at",
    "outcome_source",
    "outcome_note",
    "created_at",
})


class SchemaPatchError(RuntimeError):
    """Critical schema alignment failure — API must not serve half-broken routes."""


async def ensure_schema_patches(conn) -> None:
    """Additive schema patches for environments where create_all / alembic lag the ORM."""
    patches = [
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
        ALTER TABLE mira_users
        ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ NULL
        """,
        """
        ALTER TABLE mira_org_invites
        ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'coordinator'
        """,
        """
        ALTER TABLE training_events
        ADD COLUMN IF NOT EXISTS outcome_period VARCHAR(40) NULL
        """,
        """
        ALTER TABLE training_events
        ADD COLUMN IF NOT EXISTS outcome_source VARCHAR(40) NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_training_events_tenant_outcome_period
        ON training_events (tenant_id, outcome_period)
        """,
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

    critical_failures: list[str] = []
    for sql in patches:
        try:
            await conn.execute(text(sql))
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            if "mira_users" in sql or "mira_org_invites" in sql:
                print(f"Aviso schema patch (não crítico): {msg}")
                continue
            lower = msg.lower()
            if any(
                tok in lower
                for tok in (
                    "permission",
                    "password",
                    "could not connect",
                    "timeout",
                    "authentication",
                )
            ):
                critical_failures.append(msg)
                continue
            print(f"Aviso schema patch: {msg}")

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

    if critical_failures:
        raise SchemaPatchError(
            "Falha crítica ao aplicar patches de schema: " + "; ".join(critical_failures[:3])
        )


async def verify_intervention_logs_schema(conn) -> None:
    exists = await conn.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'public' AND table_name = 'intervention_logs'
            )
            """
        )
    )
    if not bool(exists.scalar()):
        raise SchemaPatchError(
            "Tabela intervention_logs ausente. Execute alembic upgrade head "
            "(AUTO_MIGRATE) antes de servir rotas de retenção."
        )

    result = await conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'intervention_logs'
            """
        )
    )
    present = {row[0] for row in result.fetchall()}
    missing = sorted(_INTERVENTION_LOG_REQUIRED_COLUMNS - present)
    if missing:
        raise SchemaPatchError(
            "intervention_logs sem colunas exigidas pelo ORM: "
            + ", ".join(missing)
            + ". Patches aditivos e/ou alembic upgrade head são necessários."
        )


_dev_schema_patches = ensure_schema_patches


async def init_db():
    from app.models import student, tenant, intervention  # noqa: F401
    from app.models import auth, control_center  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_schema_patches(conn)
        await verify_intervention_logs_schema(conn)


async def apply_runtime_schema_patches() -> None:
    async with engine.begin() as conn:
        await ensure_schema_patches(conn)
        await verify_intervention_logs_schema(conn)
