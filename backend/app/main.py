from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from starlette.requests import Request

from app.core.config import get_settings
from app.api import (
    upload, health, scoring, connectors, jacad, sponte, sophia, sophia_sync,
    outcomes, academic_outcomes, outcome_analytics, agents, auth, mfa, delivery_webhooks, org, billing,
    retention_campaigns, retention_campaign_execution, retention_campaign_intelligence, retention_campaign_proposal_workflow, retention_campaign_scheduling, control_center_auth,
    control_center_admin, mira_admin, work_activities, student_work_timeline, composio,
    signals, student_groups, totvs_rm_operations, connector_destinations, tenant_rbac, omie, onboarding,
    smart_import, custom_fields, object_index, object_views, native_academic, academic_catalog, academic_portal, academic_operations, student_services, student_service_operations, student_finance_composio, student_document_attestation, finance_reconciliation, student_payments, asaas_official, dispatch, dispatch_integrations, dispatch_interventions, dispatch_providers, dispatch_native_webhooks, dispatch_source_keys, dispatch_composio, collections,
)
from app.db.session import init_db, apply_runtime_schema_patches, SchemaPatchError
from app.ml.model import load_model

settings = get_settings()

_DEFAULT_SECRET_KEY = "change-this-in-production"
_DEV_ADMIN_EMAIL = "admin@mira.local"
_DEV_ADMIN_PASSWORD = "MiraAdmin123!"


def _run_alembic_upgrade() -> None:
    """Apply pending migrations (additive). Used when AUTO_MIGRATE=true."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(cfg, "head")


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

    if settings.auto_migrate:
        try:
            print("AUTO_MIGRATE habilitado: executando alembic upgrade head...")
            _run_alembic_upgrade()
            print("Migrations aplicadas (alembic upgrade head).")
        except Exception as e:
            print(f"ERRO ao aplicar migrations: {e}")
            raise

    try:
        if settings.app_env == "development":
            await init_db()
            print("Tabelas prontas (create_all + patches + verificação em development).")
        else:
            await apply_runtime_schema_patches()
            print("Schema patches aditivos aplicados e intervention_logs verificado.")
    except SchemaPatchError as e:
        print(f"ERRO CRÍTICO de schema: {e}")
        raise
    except Exception as e:
        print(f"ERRO ao alinhar schema: {e}")
        raise

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
                t = Tenant(
                    slug="default", name="IES Demo", is_active=True,
                    api_key_hash=hash_api_key(settings.dev_api_key),
                )
                session.add(t)
                await session.commit()
                await session.refresh(t)
                print("Tenant default criado; credencial de API omitida dos logs.")
            elif not t.api_key_hash:
                t.api_key_hash = hash_api_key(settings.dev_api_key)
                await session.commit()
                print("API key hash do tenant default atualizado.")

            if settings.app_env == "development" and t:
                existing = await session.execute(select(User).where(User.email == _DEV_ADMIN_EMAIL))
                admin = existing.scalar_one_or_none()
                if not admin:
                    admin = User(
                        tenant_id=t.id, display_name="Admin Mira", email=_DEV_ADMIN_EMAIL,
                        password_hash=hash_password(_DEV_ADMIN_PASSWORD), role="admin", is_active=True,
                    )
                    session.add(admin)
                    await session.commit()
                    print("Usuário admin de desenvolvimento criado; senha omitida dos logs.")
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
    version="0.8.2-signals-foundation",
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
    ["*"] if settings.debug and settings.app_env == "development"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware, allow_origins=_cors, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(composio.router, prefix="/api/v1")
app.include_router(omie.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1", tags=["Upload & Students"])
app.include_router(object_index.router, prefix="/api/v1")
app.include_router(object_views.router, prefix="/api/v1")
app.include_router(smart_import.router, prefix="/api/v1", tags=["Importação inteligente"])
app.include_router(native_academic.router, prefix="/api/v1")
app.include_router(native_academic.portal_router, prefix="/api/v1")
app.include_router(academic_catalog.router, prefix="/api/v1")
app.include_router(academic_portal.router, prefix="/api/v1")
app.include_router(academic_operations.institution_router, prefix="/api/v1")
app.include_router(academic_operations.portal_router, prefix="/api/v1")
app.include_router(student_services.portal_router, prefix="/api/v1")
app.include_router(student_services.institution_router, prefix="/api/v1")
app.include_router(student_service_operations.portal_router, prefix="/api/v1")
app.include_router(student_service_operations.institution_router, prefix="/api/v1")
app.include_router(student_finance_composio.router, prefix="/api/v1")
app.include_router(finance_reconciliation.router, prefix="/api/v1")
app.include_router(student_payments.router, prefix="/api/v1")
app.include_router(student_payments.portal_router, prefix="/api/v1")
app.include_router(student_payments.sandbox_router, prefix="/api/v1")
app.include_router(asaas_official.router, prefix="/api/v1")
app.include_router(asaas_official.portal, prefix="/api/v1")
app.include_router(asaas_official.incoming, prefix="/api/v1")
app.include_router(student_document_attestation.institution_router, prefix="/api/v1")
app.include_router(student_document_attestation.portal_router, prefix="/api/v1")
app.include_router(student_document_attestation.public_router, prefix="/api/v1")
app.include_router(custom_fields.router, prefix="/api/v1", tags=["Campos personalizados"])
app.include_router(dispatch.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")
app.include_router(dispatch_integrations.router, prefix="/api/v1")
app.include_router(dispatch_interventions.router, prefix="/api/v1")
app.include_router(dispatch_providers.router, prefix="/api/v1")
app.include_router(dispatch_native_webhooks.router, prefix="/api/v1")
app.include_router(dispatch_source_keys.router, prefix="/api/v1")
app.include_router(dispatch_composio.router, prefix="/api/v1")
app.include_router(scoring.router, prefix="/api/v1", tags=["Motor Preditivo (Risk + SHAP)"])
app.include_router(connectors.router, prefix="/api/v1", tags=["Conectores ERP/LMS"])
app.include_router(connector_destinations.router, prefix="/api/v1")
app.include_router(jacad.router, prefix="/api/v1")
app.include_router(sponte.router, prefix="/api/v1")
app.include_router(sophia.router, prefix="/api/v1")
app.include_router(sophia_sync.router, prefix="/api/v1")
app.include_router(outcomes.router, prefix="/api/v1", tags=["Learning Loop (Outcomes)"])
app.include_router(academic_outcomes.router, prefix="/api/v1", tags=["Outcomes acadêmicos"])
app.include_router(outcome_analytics.router, prefix="/api/v1", tags=["Resultados de permanência"])
app.include_router(agents.router, prefix="/api/v1", tags=["Agentes de Retencao"])
app.include_router(retention_campaigns.router, prefix="/api/v1")
app.include_router(retention_campaign_execution.router, prefix="/api/v1")
app.include_router(retention_campaign_intelligence.router, prefix="/api/v1")
app.include_router(retention_campaign_proposal_workflow.router, prefix="/api/v1")
app.include_router(retention_campaign_scheduling.router, prefix="/api/v1")
app.include_router(delivery_webhooks.router, prefix="/api/v1", tags=["Webhooks de entrega"])
app.include_router(auth.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(mfa.router, prefix="/api/v1")
app.include_router(org.router, prefix="/api/v1")
app.include_router(tenant_rbac.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(work_activities.router, prefix="/api/v1")
app.include_router(student_work_timeline.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(student_groups.router, prefix="/api/v1")
app.include_router(totvs_rm_operations.router, prefix="/api/v1")
app.include_router(control_center_auth.router, prefix="/api/v1")
app.include_router(control_center_admin.router, prefix="/api/v1")
app.include_router(mira_admin.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "project": settings.app_name, "version": "0.8.2-signals-foundation",
        "phase": "Wave 1.1 — fundação Inteligência de Sinais", "status": "running",
        "docs": "/docs", "signals": "/api/v1/signals/catalog · /evaluate · /summary",
        "work": "/api/v1/work/activities · /api/v1/students/{id}/work-timeline",
    }
