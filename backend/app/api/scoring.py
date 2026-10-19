"""Endpoints do Motor Preditivo de Risco."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, Any

from app.db.session import get_db
from app.models.student import Student
from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT
from app.ml.scoring import (
    score_batch, score_student_dict, score_all_pending, get_model_info,
)
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
    risk_level: str
    probability: float
    shap_top_factors: list[dict[str, Any]]
    shap_summary: str
    features_used: dict[str, float]


@router.get("/model/info")
async def model_info():
    return get_model_info()


@router.post("/model/train")
async def retrain_model(n_samples: int = Query(4000, ge=500, le=20000)):
    metrics = train_model(n_samples=n_samples)
    return {"message": "Modelo retreinado com sucesso", "metrics": metrics}


@router.post("/predict", response_model=PredictResponse)
async def predict_single(payload: StudentFeaturesInput):
    result = score_student_dict(payload.model_dump())
    return PredictResponse(**result)


@router.post("/score/batch/{batch_id}")
async def score_batch_endpoint(
    batch_id: str,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await score_batch(db, batch_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao pontuar batch: {str(e)}")


@router.post("/score/pending")
async def score_pending_endpoint(db: AsyncSession = Depends(get_db)):
    try:
        return await score_all_pending(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk/summary")
async def risk_summary(batch_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    base = select(Student.risk_level, func.count(Student.id)).where(
        Student.risk_score.is_not(None)
    )
    if batch_id:
        base = base.where(Student.batch_id == batch_id)
    base = base.group_by(Student.risk_level)
    result = await db.execute(base)
    rows = result.all()
    summary = {"baixo": 0, "medio": 0, "critico": 0, "sem_score": 0}
    total_scored = 0
    for level, count in rows:
        if level in summary:
            summary[level] = count
            total_scored += count
    q_pending = select(func.count(Student.id)).where(Student.risk_score.is_(None))
    if batch_id:
        q_pending = q_pending.where(Student.batch_id == batch_id)
    pending = (await db.execute(q_pending)).scalar() or 0
    summary["sem_score"] = pending
    return {
        "summary": summary,
        "total_scored": total_scored,
        "total_students": total_scored + pending,
        "batch_id": batch_id,
    }


@router.get("/risk/critical")
async def list_critical_students(
    batch_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Student)
        .where(Student.risk_level == "critico")
        .order_by(Student.risk_score.desc())
        .limit(limit)
    )
    if batch_id:
        query = query.where(Student.batch_id == batch_id)
    result = await db.execute(query)
    students = result.scalars().all()
    return {
        "count": len(students),
        "students": [
            {
                "id": s.id,
                "matricula": s.matricula,
                "nome": s.nome,
                "curso": s.curso,
                "turma": s.turma,
                "semestre": s.semestre,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "shap_summary": (s.shap_top_factors or {}).get("summary"),
                "shap_top_factors": (s.shap_top_factors or {}).get("top_3"),
                "dias_atraso_boleto": s.dias_atraso_boleto,
                "dias_sem_login": s.dias_sem_login,
                "presenca_percentual": s.presenca_percentual,
                "nota_media": s.nota_media,
            }
            for s in students
        ],
    }


@router.get("/students/{student_id}/risk")
async def get_student_risk(student_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado")
    return {
        "id": student.id,
        "matricula": student.matricula,
        "nome": student.nome,
        "curso": student.curso,
        "turma": student.turma,
        "semestre": student.semestre,
        "forma_ingresso": student.forma_ingresso,
        "features": {
            "dias_atraso_boleto": student.dias_atraso_boleto,
            "recorrencia_atrasos": student.recorrencia_atrasos,
            "dias_sem_login": student.dias_sem_login,
            "presenca_percentual": student.presenca_percentual,
            "nota_media": student.nota_media,
            "reprovacoes": student.reprovacoes,
        },
        "risk_score": student.risk_score,
        "risk_level": student.risk_level,
        "shap_top_factors": student.shap_top_factors,
    }


@router.get("/model/feature-importance")
async def feature_importance():
    from app.ml.model import load_model
    import numpy as np
    model = load_model()
    importance = model.feature_importances_
    pairs = sorted(zip(FEATURE_COLUMNS, importance), key=lambda x: -x[1])
    total = float(np.sum(importance)) + 1e-9
    return {
        "features": [
            {
                "feature": feat,
                "label": FEATURE_LABELS_PT.get(feat, feat),
                "importance": round(float(imp), 4),
                "importance_pct": round(float(imp / total * 100), 1),
            }
            for feat, imp in pairs
        ]
    }
