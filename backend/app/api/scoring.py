"""Endpoints do Motor Preditivo — isolados por tenant via AuthContext."""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from uuid import uuid5, NAMESPACE_URL

from app.db.session import get_db
from app.core.auth import AuthContext, get_current_tenant
from app.models.student import Student
from app.models.risk_assessment import RiskAssessment
from app.models.intervention import InterventionLog
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
    model_info = get_model_info()
    model_version = model_info.get("version")
    if not model_version:
        raise HTTPException(
            status_code=503,
            detail="Versão do modelo base indisponível; previsão what-if bloqueada para preservar rastreabilidade.",
        )
    base = score_student_dict(payload.model_dump())
    scenarios = []
    if payload.dias_atraso_boleto and payload.dias_atraso_boleto > 0:
        s = payload.model_dump()
        s["dias_atraso_boleto"] = 0
        s["recorrencia_atrasos"] = max(0, (payload.recorrencia_atrasos or 0) - 1)
        r = score_student_dict(s)
        scenarios.append({
            "name": "Quitar boleto", "risk_score": r["risk_score"], "risk_level": r["risk_level"],
            "delta": round(r["risk_score"] - base["risk_score"], 1),
            "model_scope": "base", "model_version": str(model_version),
        })
    return {
        "current": {
            "risk_score": base["risk_score"], "risk_level": base["risk_level"],
            "recommended_actions": base.get("recommended_actions", []),
            "model_scope": "base", "model_version": str(model_version),
        },
        "scenarios": scenarios,
    }


@router.post("/score/batch/{batch_id}")
async def score_batch_endpoint(
    batch_id: str,
    force: bool = Query(False),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if force and not idempotency_key:
        raise HTTPException(status_code=422, detail="force=true exige o cabeçalho Idempotency-Key para evitar avaliações duplicadas em retries.")
    if idempotency_key and (len(idempotency_key) > 200 or not idempotency_key.strip()):
        raise HTTPException(status_code=422, detail="Idempotency-Key deve conter de 1 a 200 caracteres.")
    run_id = str(uuid5(NAMESPACE_URL, "mira-risk:" + auth.tenant_id + ":" + batch_id + ":" + idempotency_key)) if idempotency_key else None
    try:
        return await score_batch(
            db, batch_id, force=force, tenant_id=auth.tenant_id,
            tenant_slug=auth.tenant_slug, scoring_run_id=run_id,
        )
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




_VALID_RISK_LEVELS = {"baixo", "medio", "critico"}


def _utc(value: datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _assessment_payload(row: RiskAssessment, student: Student | None = None) -> dict[str, Any]:
    return {
        "id": row.id, "student_id": row.student_id, "tenant_id": row.tenant_id,
        "student_name": student.nome if student else None,
        "matricula": student.matricula if student else None,
        "course": student.curso if student else None,
        "evaluated_at": row.evaluated_at.isoformat(), "score": row.score,
        "risk_level": row.risk_level, "model_version": row.model_version,
        "score_semantics_version": row.score_semantics_version,
        "model_scope": row.model_scope, "model_score": row.model_score,
        "dynamic_adjustment": row.dynamic_adjustment,
        "explanation": row.explanation if row.explanation and row.explanation.get("available") else None,
        "explanation_available": bool(row.explanation and row.explanation.get("available")),
        "scoring_run_id": row.scoring_run_id, "batch_id": row.batch_id,
    }


def _change_type(current: RiskAssessment, previous: RiskAssessment | None) -> tuple[str, float | None]:
    if previous is None:
        return "sem_historico_comparavel", None
    if (not current.model_version or not previous.model_version or current.model_version != previous.model_version or current.model_scope != previous.model_scope or not current.score_semantics_version or current.score_semantics_version != previous.score_semantics_version):
        return "mudanca_modelo", None
    delta = round(float(current.score) - float(previous.score), 1)
    if delta > 0:
        return "risco_aumentou", delta
    if delta < 0:
        return "risco_diminuiu", delta
    return "sem_mudanca_relevante", delta


@router.get("/risk/history")
async def risk_history(
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    course: str | None = Query(default=None, max_length=150),
    risk_level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Consulta histórica; não calcula novo score. Todas as leituras são tenant-scoped."""
    now = datetime.now(timezone.utc)
    end = _utc(to_date, now)
    start = _utc(from_date, end - timedelta(days=90))
    if start > end:
        raise HTTPException(status_code=422, detail="'from' deve ser anterior ou igual a 'to'.")
    if risk_level and risk_level not in _VALID_RISK_LEVELS:
        raise HTTPException(status_code=422, detail="risk_level inválido.")
    course_filter = course.strip() if course and course.strip() else None
    query = select(RiskAssessment, Student).join(Student, Student.id == RiskAssessment.student_id).where(
        RiskAssessment.tenant_id == auth.tenant_id,
        Student.tenant_id == auth.tenant_id,
        RiskAssessment.evaluated_at >= start,
        RiskAssessment.evaluated_at <= end,
    )
    if course_filter:
        query = query.where(Student.curso.ilike("%" + course_filter + "%"))
    if risk_level:
        query = query.where(RiskAssessment.risk_level == risk_level)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    students_total_query = select(func.count(func.distinct(RiskAssessment.student_id))).select_from(
        RiskAssessment
    ).join(Student, Student.id == RiskAssessment.student_id).where(
        RiskAssessment.tenant_id == auth.tenant_id,
        Student.tenant_id == auth.tenant_id,
        RiskAssessment.evaluated_at >= start,
        RiskAssessment.evaluated_at <= end,
        *([Student.curso.ilike("%" + course_filter + "%")] if course_filter else []),
        *([RiskAssessment.risk_level == risk_level] if risk_level else []),
    )
    students_total = (await db.execute(students_total_query)).scalar_one()
    page_rows = (await db.execute(
        query.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    temporal_rows = (await db.execute(
        query.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc()).limit(5000)
    )).all()
    # Movement comparisons use each student's latest assessment in the period,
    # even when a risk-level filter is active. The filter is applied after selecting
    # the latest assessment so it cannot accidentally promote an older score.
    movement_query = select(RiskAssessment, Student).join(
        Student, Student.id == RiskAssessment.student_id
    ).where(
        RiskAssessment.tenant_id == auth.tenant_id,
        Student.tenant_id == auth.tenant_id,
        RiskAssessment.evaluated_at >= start,
        RiskAssessment.evaluated_at <= end,
        *([Student.curso.ilike("%" + course_filter + "%")] if course_filter else []),
    )
    movement_rows = (await db.execute(
        movement_query.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc()).limit(5000)
    )).all()
    movement_student_by_id = {row.student_id: student for row, student in movement_rows}
    current_by_student: dict[str, RiskAssessment] = {}
    for row, _student in movement_rows:
        current_by_student.setdefault(row.student_id, row)
    previous_by_student: dict[str, RiskAssessment] = {}
    if current_by_student:
        ranked = select(
            RiskAssessment.id.label("assessment_id"),
            func.row_number().over(
                partition_by=RiskAssessment.student_id,
                order_by=(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc()),
            ).label("rn"),
        ).where(
            RiskAssessment.tenant_id == auth.tenant_id,
            RiskAssessment.student_id.in_(list(current_by_student.keys())),
            RiskAssessment.evaluated_at <= end,
        ).subquery()
        previous_rows = (await db.execute(
            select(RiskAssessment).join(ranked, ranked.c.assessment_id == RiskAssessment.id)
            .where(ranked.c.rn == 2, RiskAssessment.tenant_id == auth.tenant_id)
        )).scalars().all()
        previous_by_student = {row.student_id: row for row in previous_rows}
    movements = []
    counts = defaultdict(int)
    classification_changes = 0
    for student_id, current in current_by_student.items():
        if risk_level and current.risk_level != risk_level:
            continue
        previous = previous_by_student.get(student_id)
        change_type, delta = _change_type(current, previous)
        counts[change_type] += 1
        if previous and delta is not None and previous.risk_level != current.risk_level:
            classification_changes += 1
        student = movement_student_by_id.get(student_id)
        movements.append({
            "student_id": student_id, "student_name": student.nome if student else None,
            "matricula": student.matricula if student else None, "course": student.curso if student else None,
            "previous_score": previous.score if previous else None,
            "previous_risk_level": previous.risk_level if previous else None,
            "previous_evaluated_at": previous.evaluated_at.isoformat() if previous else None,
            "current_score": current.score, "current_risk_level": current.risk_level,
            "current_evaluated_at": current.evaluated_at.isoformat(), "delta": delta,
            "change_type": change_type, "model_version": current.model_version,
            "previous_model_version": previous.model_version if previous else None,
        })
    order = {"risco_aumentou": 0, "mudanca_modelo": 1, "sem_historico_comparavel": 2, "risco_diminuiu": 3, "sem_mudanca_relevante": 4}
    movements.sort(key=lambda item: (order.get(item["change_type"], 9), -(item["delta"] or 0), item["student_name"] or "", item["student_id"]))
    # Latest real assessment per student per week. Version-specific groups prevent
    # score averages from mixing model versions.
    representative: dict[tuple[str, str], tuple[RiskAssessment, Student]] = {}
    for row, student in temporal_rows:
        d = row.evaluated_at.date()
        bucket = (d - timedelta(days=d.weekday())).isoformat()
        key = (row.student_id, bucket)
        if key not in representative or row.evaluated_at > representative[key][0].evaluated_at:
            representative[key] = (row, student)
    grouped: dict[tuple[str, str, str], list[RiskAssessment]] = defaultdict(list)
    for (_student_id, bucket), (row, _student) in representative.items():
        grouped[(bucket, row.model_scope, row.model_version or "versao_indisponivel")].append(row)
    timeline = []
    for (bucket, scope, version), rows in sorted(grouped.items()):
        group_distribution = {"baixo": 0, "medio": 0, "critico": 0, "students_count": len(rows)}
        for assessment in rows:
            group_distribution[assessment.risk_level] += 1
        timeline.append({
            "bucket": bucket, "model_scope": scope, "model_version": version,
            "average_score": round(sum(float(r.score) for r in rows) / len(rows), 2),
            "students_count": len(rows), "risk_distribution": group_distribution,
        })
    course_rows = (await db.execute(
        select(Student.curso).join(RiskAssessment, RiskAssessment.student_id == Student.id).where(
            RiskAssessment.tenant_id == auth.tenant_id, Student.tenant_id == auth.tenant_id,
            RiskAssessment.evaluated_at >= start, RiskAssessment.evaluated_at <= end,
            Student.curso.is_not(None),
        ).distinct().order_by(Student.curso)
    )).all()
    courses = [row[0] for row in course_rows if row[0]]
    return {
        "tenant_id": auth.tenant_id, "period": {"from": start.isoformat(), "to": end.isoformat()},
        "filters": {"course": course_filter, "risk_level": risk_level},
        "total_assessments": total, "students_with_assessments": students_total,
        "temporal_data_truncated": total > len(temporal_rows) or len(movement_rows) >= 5000,
        "temporal_rows_limit": 5000,
        "comparison_counts": {
            "increased": counts["risco_aumentou"], "decreased": counts["risco_diminuiu"],
            "unchanged": counts["sem_mudanca_relevante"], "model_changed": counts["mudanca_modelo"],
            "no_comparable_history": counts["sem_historico_comparavel"],
            "classification_changed": classification_changes,
        },
        "timeline": timeline, "courses": courses, "movements": movements[:500], "movements_truncated": len(movements) > 500 or len(movement_rows) >= 5000,
        "assessments": [
            {**_assessment_payload(row, student), "student_name": student.nome, "course": student.curso}
            for row, student in page_rows
        ],
        "pagination": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size},
        "definition": "Aumento significa delta positivo na escala 0–100 (score maior = maior risco). 'Sem mudança relevante' significa delta exatamente zero; não há limiar científico configurado.",
    }


@router.get("/students/{student_id}/risk/history")
async def student_risk_history(
    student_id: str,
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Trajetória e intervenções do aluno autenticado; nunca recalcula scores."""
    student = (await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    now = datetime.now(timezone.utc)
    end = _utc(to_date, now)
    start = _utc(from_date, end - timedelta(days=365))
    if start > end:
        raise HTTPException(status_code=422, detail="'from' deve ser anterior ou igual a 'to'.")
    base = select(RiskAssessment).where(
        RiskAssessment.tenant_id == auth.tenant_id, RiskAssessment.student_id == student_id,
        RiskAssessment.evaluated_at >= start, RiskAssessment.evaluated_at <= end,
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    rows.reverse()
    logs = (await db.execute(
        select(InterventionLog).where(
            InterventionLog.tenant_id == auth.tenant_id, InterventionLog.student_id == student_id,
            InterventionLog.created_at >= start, InterventionLog.created_at <= end,
        ).order_by(InterventionLog.created_at.asc()).limit(200)
    )).scalars().all()
    return {
        "student": {"id": student.id, "name": student.nome, "matricula": student.matricula, "course": student.curso, "tenant_id": auth.tenant_id},
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "assessments": [_assessment_payload(row, student) for row in rows],
        "total_assessments": total,
        "pagination": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size},
        "interventions": [{
            "id": log.id, "created_at": log.created_at.isoformat(), "channel": log.channel,
            "status": log.status, "risk_score": log.risk_score, "risk_level": log.risk_level,
            "decision_reason": log.decision_reason, "outcome": log.outcome,
            "outcome_at": log.outcome_at.isoformat() if log.outcome_at else None,
        } for log in logs],
        "explanation_note": "Fatores são exibidos apenas quando foram preservados na avaliação original; nenhuma explicação histórica é recalculada nesta consulta.",
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
