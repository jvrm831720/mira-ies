"""
Fixtures de teste de integracao — usa Postgres real (igual ao docker-compose.yml),
nao SQLite, porque os modelos usam tipos especificos do dialeto (UUID, JSONB).

Requer um Postgres acessivel (local via `docker-compose up -d db` ou o servico
Postgres do CI). O banco de teste e derivado do banco de dev (sufixo `_test`) e
e criado automaticamente se nao existir.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import make_url

_DEFAULT_DEV_DATABASE_URL = "postgresql+asyncpg://beacon:beacon_secret@127.0.0.1:5433/beacon"
_base_url = make_url(os.environ.get("DATABASE_URL", _DEFAULT_DEV_DATABASE_URL))
_test_db_name = _base_url.database if (_base_url.database or "").endswith("_test") else f"{_base_url.database}_test"
_test_url = _base_url.set(database=_test_db_name)
_admin_url = _base_url.set(database="postgres")

# Precisa rodar ANTES de qualquer import de `app.*` — o engine e os settings sao
# construidos na importacao e ficam cacheados (lru_cache / modulo global).
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use"
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ.setdefault("ALLOW_FORCE_TRAIN", "true")
os.environ.setdefault("ALLOW_FORCE_ACTIVATE", "true")
os.environ.setdefault("ALLOW_UNSIGNED_WEBHOOKS", "true")
os.environ.setdefault("SHAP_ON_BATCH", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import asyncpg  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.db.session as db_session_module  # noqa: E402

# pytest-asyncio (modo "auto") da um event loop NOVO por teste por padrao.
# O engine assincrono padrao do app usa um pool com conexoes de vida longa,
# que ficam presas ao loop em que nasceram — reusa-las num teste seguinte
# (loop diferente) explode com "Future attached to a different loop".
# NullPool elimina o reuso: cada operacao abre/fecha sua propria conexao
# dentro do loop corrente, entao funciona com qualquer escopo de loop.
db_session_module.engine = create_async_engine(
    os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
)
db_session_module.AsyncSessionLocal = async_sessionmaker(
    db_session_module.engine, class_=AsyncSession, expire_on_commit=False,
)


def _asyncpg_dsn(url) -> str:
    return f"postgresql://{url.username}:{url.password}@{url.host}:{url.port}/{url.database}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_test_database():
    conn = await asyncpg.connect(_asyncpg_dsn(_admin_url))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", _test_db_name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{_test_db_name}"')
    finally:
        await conn.close()

    import app.models.student  # noqa: F401
    import app.models.tenant  # noqa: F401
    import app.models.intervention  # noqa: F401
    import app.models.consent  # noqa: F401
    import app.models.engagement  # noqa: F401

    async with db_session_module.engine.begin() as sa_conn:
        await sa_conn.run_sync(db_session_module.Base.metadata.drop_all)
        await sa_conn.run_sync(db_session_module.Base.metadata.create_all)
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    yield
    async with db_session_module.engine.begin() as conn:
        for table in reversed(db_session_module.Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db_session():
    async with db_session_module.AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def tenant_factory(db_session):
    from app.core.security import generate_api_key, hash_api_key
    from app.models.tenant import Tenant

    async def _create(slug: str = "acme", name: str = "Acme University", webhook_secret: str | None = None):
        raw_key = generate_api_key()
        t = Tenant(slug=slug, name=name, is_active=True, api_key_hash=hash_api_key(raw_key), webhook_secret=webhook_secret)
        db_session.add(t)
        await db_session.commit()
        await db_session.refresh(t)
        return t, raw_key

    return _create


@pytest_asyncio.fixture
async def tenant(tenant_factory):
    return await tenant_factory()


@pytest_asyncio.fixture
async def institutional_training_authorization(tenant, db_session):
    """Provide explicit local-training authorization for tests that train models."""
    from datetime import datetime, timedelta, timezone

    from app.models.control_center import AdminPrincipal
    from app.models.institutional_training_authorization import InstitutionalTrainingAuthorization

    t, _raw_key = tenant
    admin = AdminPrincipal(
        email=f"training-admin-{t.slug}@example.test",
        display_name="Training Test Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    db_session.add(InstitutionalTrainingAuthorization(
        tenant_id=t.id,
        contract_reference=f"test-contract-{t.slug}",
        contract_version="v1",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        approved_by_admin_id=admin.id,
        evidence_reference=f"test-evidence://{t.slug}",
        dataset_eligibility_reference=f"test-dataset://{t.slug}",
    ))
    await db_session.commit()
    return t


@pytest_asyncio.fixture
def auth_headers(tenant):
    _t, raw_key = tenant
    return {"X-API-Key": raw_key}
