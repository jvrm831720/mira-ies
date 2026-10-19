from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.api import upload, health, scoring, connectors
from app.db.session import init_db
from app.ml.model import load_model

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"{settings.app_name} starting in {settings.app_env} mode...")
    print("Inicializando tabelas no banco (Supabase / PostgreSQL)...")
    try:
        await init_db()
        print("Tabelas prontas.")
    except Exception as e:
        print(f"Aviso ao criar tabelas: {e}")
        print("Verifique a DATABASE_URL no .env (Supabase connection string).")

    print("Carregando motor preditivo (XGBoost + SHAP)...")
    try:
        load_model()
        print("Modelo de risco pronto.")
    except Exception as e:
        print(f"Aviso ao carregar modelo: {e}")

    yield
    print("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Plataforma de Predicao e Retencao Ativa de Alunos (MVP)\n\n"
        "## Motor Preditivo\n"
        "- XGBoost + SHAP\n"
        "- Risk Score 0-100\n"
        "- Top 3 fatores causais explicaveis\n\n"
        "## Conectores\n"
        "- JACAD, Sponte, SophiA, GVcollege, WPensar/Isaac\n"
        "- Moodle, Canvas\n"
        "- JSON canonico + webhooks"
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(upload.router, prefix="/api/v1", tags=["Upload & Students"])
app.include_router(scoring.router, prefix="/api/v1", tags=["Motor Preditivo (Risk + SHAP)"])
app.include_router(connectors.router, prefix="/api/v1", tags=["Conectores ERP/LMS"])


@app.get("/")
async def root():
    return {
        "project": settings.app_name,
        "version": "0.3.0",
        "phase": "01+02 - Ingestao multi-fonte + Motor Preditivo",
        "status": "running",
        "docs": "/docs",
        "database": "Supabase Cloud (PostgreSQL)",
        "ml": "XGBoost + SHAP ready",
        "connectors": "GET /api/v1/connectors",
    }
