from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import secrets
from starlette.requests import Request

from app.core.config import get_settings
from app.api import upload, health, scoring, connectors, outcomes, agents, auth, delivery_webhooks, org, billing
from app.db.session import init_db
from app.ml.model import load_model

settings = get_settings()

_DEFAULT_SECRET_KEY = "change-this-in-production"
_DEV_ADMIN_EMAIL = "admin@mira.local"
_DEV_ADMIN_PASSWORD = "MiraAdmin123!"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env != "development" and (
        settings.secret_key == _DEFAULT_SECRET_KEY
        or "change-this" in settings.secret_key.lower()
        or len(settings.secret_key) < 32
    ):
        raise RuntimeError(
            "SECRET_KEY padrao, placeholder ou curto detectado fora de development. "
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
        from app.core.mira_security import hash_password
        from app.db.session import AsyncSessionLocal
        from app.models.tenant import Tenant
        from app.models.auth import User
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            r = await session.execute(select(Tenant).where(Tenant.slug == "default"))
            t = r.scalar_one_or_none()
            if not t:
                bootstrap_key = (
                    settings.dev_api_key
                    if settings.app_env == "development"
                    else secrets.token_urlsafe(32)
                )
                t = Tenant(
                    slug="default",
                    name="IES Demo",
                    is_active=True,
                    api_key_hash=hash_api_key(bootstrap_key),
                )
                session.add(t)
                await session.commit()
                await session.refresh(t)
                print("Tenant default criado.")
            elif not t.api_key_hash:
                bootstrap_key = (
                    settings.dev_api_key
                    if settings.app_env == "development"
                    else secrets.token_urlsafe(32)
                )
                t.api_key_hash = hash_api_key(bootstrap_key)
                await session.commit()
                print("API key hash do tenant default atualizado.")

            if settings.app_env == "development" and t:
                existing = await session.execute(select(User).where(User.email == _DEV_ADMIN_EMAIL))
                admin = existing.scalar_one_or_none()
                if not admin:
                    admin = User(
                        tenant_id=t.id,
                        display_name="Admin Mira",
                        email=_DEV_ADMIN_EMAIL,
                        password_hash=hash_password(_DEV_ADMIN_PASSWORD),
                        role="admin",
                        is_active=True,
                    )
                    session.add(admin)
                    await session.commit()
                    print(
                        f"Usuário admin de desenvolvimento criado: {_DEV_ADMIN_EMAIL} / {_DEV_ADMIN_PASSWORD}"
                    )
                else:
                    print(f"Admin de desenvolvimento já existe: {_DEV_ADMIN_EMAIL}")
    except Exception as e:
        print(f"Aviso bootstrap tenant/admin: {e}")

    try:
        load_model()
        print("Modelo de risco pronto.")
    except Exception as e:
        print(f"Aviso ao carregar modelo: {e}")
    yield
    print("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    description="Mira — permanência estudantil, autenticação e isolamento multi-tenant",
    version="0.7.0-billing",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = []
    for error in exc.errors():
        sanitized = dict(error)
        sanitized.pop("input", None)
        safe_errors.append(sanitized)
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": safe_errors}))


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
app.include_router(agents.router, prefix="/api/v1", tags=["Agentes de Retencao"])
app.include_router(delivery_webhooks.router, prefix="/api/v1", tags=["Webhooks de entrega"])
app.include_router(auth.router, prefix="/api/v1")
app.include_router(org.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "project": settings.app_name,
        "version": "0.7.0-billing",
        "phase": "Fatura e créditos por canal",
        "status": "running",
        "docs": "/docs",
        "billing": "/api/v1/billing/summary · /api/v1/billing/credits",
    }
