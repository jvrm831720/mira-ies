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


async def _dev_schema_patches(conn) -> None:
    """create_all não altera tabelas antigas — aplica patches mínimos em development."""
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
        ALTER TABLE mira_org_invites
        ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'coordinator'
        """,
        # Eventos de retenção
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
    ]
    for sql in patches:
        try:
            await conn.execute(text(sql))
        except Exception as exc:
            print(f"Aviso schema patch: {exc}")


async def init_db():
    from app.models import student, tenant, intervention  # noqa: F401
    from app.models import auth, control_center  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Patches também em produção quando create_all já rodou antes (Supabase)
        await _dev_schema_patches(conn)
