"""Endpoints do Motor Preditivo — isolados por tenant via AuthContext."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional, Any

from app.db.session import get_db
from app.core.auth import AuthContext, get_current_tenant
from app.models.student import Student
from app.services.consent import effective_preferences
from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT
from app.ml.scoring import score_batch, score_student_dict, score_all_pending, get_model_info

router = APIRouter()


class StudentFeaturesInput(BaseModel):
    matricula: Optional[str] = Field(default=None, max_length=50)
    nome: Optional[str] = Field(default=None, max_length=255)
    dias_atraso_boleto: int = Field(default=0, ge=0, le=3650)
    recorrencia_atrasos: int = Field(default=0, ge=0, le=100)
    dias_sem_login: int = Field(default=0, ge=0, le=3650)
    presenca_percentual: float = Field(default=100.0, ge=0, le=100)
    nota_media: float = Field(default=7.0, ge=0, le=10)
    reprovacoes: int = Field(default=0, ge=0, le=100)
    semestre: int = Field(default=1, ge=1, le=30)
    forma_ingresso: Optional[str] = Field(default=None, max_length=100)
    curso: Optional[str] = Field(default=None, max_length=150)


class PredictResponse(BaseModel):
    risk_score: float
    model_score: float | None = None
    risk_level: str
    probability: float
    shap_top_factors: list[dict[str, Any]]
    shap_summary: str
    features_used: dict[str, float]
    rule_flags: list[str] = []
    rule_boost: float = 0
    recommended_actions: list[str] = []
    confidence: str = "media"
    missing_features: list[str] = []
    model_scope: str
    model_version: str


@router.get("/model/info")
async def model_info():
    return get_model_info()


@router.post("/model/train")
async def retrain_model(auth: AuthContext = Depends(get_current_tenant)):
    """Fail-closed: o fluxo legado sobrescrevia o modelo global ativo sem aprovação."""
    raise HTTPException(
        status_code=409,
        detail=(
            "Treinamento global bloqueado até existir fluxo versionado com relatório, "
            "aprovação explícita, ativação controlada e rollback. O baseline sintético "
            "atual permanece disponível e não recebe dados reais de instituições."
        ),
    )


@router.post("/predict", response_model=PredictResponse)
async def predict_single(payload: StudentFeaturesInput, auth: AuthContext = Depends(get_current_tenant)):
    # This endpoint currently scores with the packaged baseline model. Never return a
    # prediction without its exact model version: callers must be able to trace it.
    model_info = get_model_info()
    model_version = model_info.get("version")
    if not model_version:
        raise HTTPException(
            status_code=503,
            detail="Versão do modelo base indisponível; previsão bloqueada para preservar rastreabilidade.",
        )
    result = score_student_dict(payload.model_dump())
    result["model_scope"] = "base"
    result["model_version"] = str(model_version)
    return PredictResponse(**result)


@router.post("/predict/what-if")
async def predict_what_if(payload: StudentFeaturesInput, auth: AuthContext = Depends(get_current_tenant)):
    base = score_student_dict(payload.model_dump())
    scenarios = []
    if payload.dias_atraso_boleto and payload.dias_atraso_boleto > 0:
        s = payload.model_dump()
        s["dias_atraso_boleto"] = 0
        s["recorrencia_atrasos"] = max(0, (payload.recorrencia_atrasos or 0) - 1)
        r = score_student_dict(s)
        scenarios.append({"name": "Quitar boleto", "risk_score": r["risk_score"], "risk_level": r["risk_level"], "delta": round(r["risk_score"] - base["risk_score"], 1)})
    return {"current": {"risk_score": base["risk_score"], "risk_level": base["risk_level"], "recommended_actions": base.get("recommended_actions", [])}, "scenarios": scenarios}


@router.post("/score/batch/{batch_id}")
async def score_batch_endpoint(
    batch_id: str,
    force: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await score_batch(db, batch_id, force=force, tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score/pending")
async def score_pending_endpoint(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    return await score_all_pending(db, tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug)


@router.get("/risk/summary")
async def risk_summary(
    batch_id: Optional[str] = None,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    base = select(Student.risk_level, func.count(Student.id)).where(
        Student.risk_score.is_not(None), Student.tenant_id == auth.tenant_id,
    )
    if batch_id:
        base = base.where(Student.batch_id == batch_id)
    base = base.group_by(Student.risk_level)
    rows = (await db.execute(base)).all()
    summary = {"baixo": 0, "medio": 0, "critico": 0, "sem_score": 0}
    total_scored = 0
    for level, count in rows:
        if level in summary:
            summary[level] = count
            total_scored += count
    q_pending = select(func.count(Student.id)).where(Student.risk_score.is_(None), Student.tenant_id == auth.tenant_id)
    if batch_id:
        q_pending = q_pending.where(Student.batch_id == batch_id)
    pending = (await db.execute(q_pending)).scalar() or 0
    summary["sem_score"] = pending
    return {"summary": summary, "total_scored": total_scored, "total_students": total_scored + pending, "tenant_id": auth.tenant_id, "batch_id": batch_id}


@router.get("/risk/critical")
async def list_critical_students(
    batch_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Student).where(Student.risk_level == "critico", Student.tenant_id == auth.tenant_id).order_by(Student.risk_score.desc()).limit(limit)
    if batch_id:
        query = query.where(Student.batch_id == batch_id)
    students = (await db.execute(query)).scalars().all()
    return {"count": len(students), "tenant_id": auth.tenant_id, "students": [{
        "id": s.id, "matricula": s.matricula, "nome": s.nome, "curso": s.curso,
        "communication_opt_out": s.communication_opt_out,
        "risk_score": s.risk_score, "risk_level": s.risk_level,
        "shap_summary": (s.shap_top_factors or {}).get("summary"),
        "recommended_actions": (s.shap_top_factors or {}).get("recommended_actions"),
    } for s in students]}


@router.get("/students/{student_id}/risk")
async def get_student_risk(
    student_id: str,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado")
    return {
        "id": student.id, "matricula": student.matricula, "nome": student.nome,
        "telefone": student.telefone, "email": student.email,
        "curso": student.curso, "semestre": student.semestre,
        "dias_atraso_boleto": student.dias_atraso_boleto,
        "communication_opt_out": student.communication_opt_out,
        "communication_preferences": effective_preferences(student),
        "behavior_properties": student.behavior_properties or {},
        "engagement_score": student.engagement_score,
        "engagement_score_updated_at": student.engagement_score_updated_at,
        "model_risk_score": student.model_risk_score,
        "dynamic_risk_adjustment": student.dynamic_risk_adjustment,
        "risk_score": student.risk_score, "risk_level": student.risk_level,
        "shap_top_factors": student.shap_top_factors,
        "recommended_actions": (student.shap_top_factors or {}).get("recommended_actions"),
        "tenant_id": auth.tenant_id,
    }


@router.get("/model/feature-importance")
async def feature_importance(auth: AuthContext = Depends(get_current_tenant)):
    from app.ml.model import load_model
    import numpy as np
    model = load_model()
    importance = model.feature_importances_
    pairs = sorted(zip(FEATURE_COLUMNS, importance), key=lambda x: -x[1])
    total = float(np.sum(importance)) + 1e-9
    return {"features": [{"feature": f, "label": FEATURE_LABELS_PT.get(f, f), "importance": round(float(i), 4), "importance_pct": round(float(i / total * 100), 1)} for f, i in pairs]}
