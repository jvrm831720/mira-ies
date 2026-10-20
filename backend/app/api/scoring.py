"""Endpoints do Motor Preditivo de Risco (protegidos por X-API-Key)."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, Any

from app.db.session import get_db
from app.core.auth import AuthContext, get_current_tenant
from app.models.student import Student
from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT
from app.ml.scoring import score_batch, score_student_dict, score_all_pending, get_model_info
from app.ml.model import train_model

router = APIRouter()


class StudentFeaturesInput(BaseModel):
    matricula: Optional[str] = None
    nome: Optional[str] = None
    dias_atraso_boleto: int = 0
    recorrencia_atrasos: int = 0
    dias_sem_login: int = 0
    presenca_percentual: float = 100.0
    nota_media: float = 7.0
    reprovacoes: int = 0
    semestre: int = 1
    forma_ingresso: Optional[str] = None
    curso: Optional[str] = None


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


@router.get("/model/info")
async def model_info():
    return get_model_info()


@router.post("/model/train")
async def retrain_model(
    n_samples: int = Query(5000, ge=500, le=20000),
    auth: AuthContext = Depends(get_current_tenant),
):
    from app.ml.model import invalidate_cache
    invalidate_cache()
    metrics = train_model(n_samples=n_samples)
    return {"message": "Modelo retreinado", "metrics": metrics}


@router.post("/predict", response_model=PredictResponse)
async def predict_single(payload: StudentFeaturesInput, auth: AuthContext = Depends(get_current_tenant)):
    return PredictResponse(**score_student_dict(payload.model_dump()))


@router.post("/predict/what-if")
async def predict_what_if(payload: StudentFeaturesInput, auth: AuthContext = Depends(get_current_tenant)):
    base = score_student_dict(payload.model_dump())
    scenarios = []
    if payload.dias_atraso_boleto and payload.dias_atraso_boleto > 0:
        s = payload.model_dump()
        s["dias_atraso_boleto"] = 0
        s["recorrencia_atrasos"] = max(0, (payload.recorrencia_atrasos or 0) - 1)
        r = score_student_dict(s)
        scenarios.append({"name": "Quitar boleto em atraso", "risk_score": r["risk_score"], "risk_level": r["risk_level"], "delta": round(r["risk_score"] - base["risk_score"], 1)})
    if payload.dias_sem_login and payload.dias_sem_login > 3:
        s = payload.model_dump()
        s["dias_sem_login"] = 1
        r = score_student_dict(s)
        scenarios.append({"name": "Retomar acesso ao AVA", "risk_score": r["risk_score"], "risk_level": r["risk_level"], "delta": round(r["risk_score"] - base["risk_score"], 1)})
    return {"current": {"risk_score": base["risk_score"], "risk_level": base["risk_level"], "recommended_actions": base.get("recommended_actions", []), "shap_summary": base.get("shap_summary")}, "scenarios": scenarios}


@router.post("/score/batch/{batch_id}")
async def score_batch_endpoint(
    batch_id: str,
    force: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await score_batch(db, batch_id, force=force, tenant_slug=auth.tenant_slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score/pending")
async def score_pending_endpoint(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    return await score_all_pending(db)


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
    return {"summary": summary, "total_scored": total_scored, "total_students": total_scored + pending, "batch_id": batch_id}


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
    return {"count": len(students), "students": [{
        "id": s.id, "matricula": s.matricula, "nome": s.nome, "curso": s.curso,
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
        "risk_score": student.risk_score, "risk_level": student.risk_level,
        "shap_top_factors": student.shap_top_factors,
        "recommended_actions": (student.shap_top_factors or {}).get("recommended_actions"),
    }


@router.get("/model/feature-importance")
async def feature_importance():
    from app.ml.model import load_model
    import numpy as np
    model = load_model()
    importance = model.feature_importances_
    pairs = sorted(zip(FEATURE_COLUMNS, importance), key=lambda x: -x[1])
    total = float(np.sum(importance)) + 1e-9
    return {"features": [{"feature": f, "label": FEATURE_LABELS_PT.get(f, f), "importance": round(float(i), 4), "importance_pct": round(float(i / total * 100), 1)} for f, i in pairs]}
