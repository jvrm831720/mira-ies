from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.api import upload, health, scoring, connectors, outcomes
from app.db.session import init_db
from app.ml.model import load_model

settings = get_settings()

_DEFAULT_SECRET_KEY = "change-this-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env != "development" and settings.secret_key == _DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY padrao detectado fora de development. "
            "Configure uma chave secreta real antes de subir em producao."
        )
    print(f"{settings.app_name} starting in {settings.app_env} mode...")
    try:
        if settings.app_env == "development":
            await init_db()
            print("Tabelas prontas (create_all em development).")
        else:
            print("Producao: use `alembic upgrade head` para schema (create_all desligado).")
    except Exception as e:
        print(f"Aviso ao criar tabelas: {e}")

    try:
        from app.core.security import hash_api_key
        from app.db.session import AsyncSessionLocal
        from app.models.tenant import Tenant
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            r = await session.execute(select(Tenant).where(Tenant.slug == "default"))
            t = r.scalar_one_or_none()
            if not t:
                t = Tenant(
                    slug="default",
                    name="IES Demo",
                    is_active=True,
                    api_key_hash=hash_api_key(settings.dev_api_key),
                )
                session.add(t)
                await session.commit()
                print(f"Tenant default criado. Dev API key: {settings.dev_api_key}")
            elif not t.api_key_hash:
                t.api_key_hash = hash_api_key(settings.dev_api_key)
                await session.commit()
                print("API key hash do tenant default atualizado.")
    except Exception as e:
        print(f"Aviso bootstrap tenant: {e}")

    try:
        load_model()
        print("Modelo de risco pronto.")
    except Exception as e:
        print(f"Aviso ao carregar modelo: {e}")
    yield
    print("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    description="Beacon MVP — Predicao de evasao + Auth + multi-tenant isolation",
    version="0.3.6",
    lifespan=lifespan,
)

_cors = (
    ["*"]
    if settings.debug and settings.app_env == "development"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(upload.router, prefix="/api/v1", tags=["Upload & Students"])
app.include_router(scoring.router, prefix="/api/v1", tags=["Motor Preditivo (Risk + SHAP)"])
app.include_router(connectors.router, prefix="/api/v1", tags=["Conectores ERP/LMS"])
app.include_router(outcomes.router, prefix="/api/v1", tags=["Learning Loop (Outcomes)"])


@app.get("/")
async def root():
    return {
        "project": settings.app_name,
        "version": "0.3.6",
        "phase": "Audit close-out — auth + tenant + model honesty",
        "status": "running",
        "docs": "/docs",
        "auth": "Header X-API-Key obrigatorio nas rotas /api/v1/*",
        "model_disclaimer": "Base treinado em sintético — score assistido, nao prediccao validada",
    }
