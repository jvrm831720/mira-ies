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
        # Papéis de acesso (admin/coordinator/operator/viewer)
        """
        ALTER TABLE mira_users
        ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'coordinator'
        """,
        # Garantir colunas de segurança caso a tabela seja bem antiga
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
    ]
    for sql in patches:
        try:
            await conn.execute(text(sql))
        except Exception as exc:
            # Tabela pode ainda não existir neste momento; create_all cuida depois
            print(f"Aviso schema patch: {exc}")


async def init_db():
    from app.models import student, tenant, intervention  # noqa: F401
    from app.models import auth  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.app_env == "development":
            await _dev_schema_patches(conn)
