"""Tenant-scoped, personal saved Object Index views.

Configuration is a small allowlisted presentation spec, not a dynamic SQL query
engine. No record results, SQL, sensitive fields, or arbitrary expressions saved.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.models.object_view import ObjectView

router = APIRouter(prefix="/object-views", tags=["Object Index / Saved Views"])
ObjectKey = Literal["students", "campaigns", "academic_classes", "academic_programs", "academic_subjects", "academic_teachers", "academic_terms", "collections"]
Op = Literal["eq", "neq", "contains", "not_contains", "starts_with", "gt", "lt", "between", "in", "before", "after", "empty"]
ALLOWED = {
    "students": {"nome": "text", "matricula": "text", "curso": "text",
                 "risk_level": "choice", "risk_score": "number", "created_at": "date", "follow_up": "display"},
    "collections": {"external_ref": "text", "status": "choice", "balance": "number", "source": "text", "updated_at": "date"},
    "campaigns": {"title": "text", "status": "choice", "objective": "text",
                  "audience_total": "number", "recommended_channels": "display", "created_at": "date"},
    "academic_classes": {"code": "text", "status": "choice", "subject_id": "text", "term_id": "text", "teacher_id": "text"},
}
for key in ['academic_programs', 'academic_subjects', 'academic_teachers', 'academic_terms']:
    ALLOWED[key] = {"name": "text", "code": "text", "status": "choice"}

OPS = {"text": {"eq", "neq", "contains", "not_contains", "starts_with", "empty"}, "choice": {"eq", "neq", "in", "empty"}, "number": {"eq", "gt", "lt", "between", "empty"}, "date": {"before", "after", "between", "empty"}}
PERMISSION = {"students": "students.view", "campaigns": "campaigns.view", "academic_classes": "students.sensitive.view", "collections": "audit.view"}

for key in ['academic_programs', 'academic_subjects', 'academic_teachers', 'academic_terms']:
    PERMISSION[key] = "students.sensitive.view"

class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=36)
    op: Op
    value: str | float | list[str | float] | None = Field(default=None)
    @field_validator("value")
    @classmethod
    def valid_value(cls, value):
        if isinstance(value, list) and (len(value) > 12 or any(isinstance(item, str) and len(item) > 150 for item in value)):
            raise ValueError("Lista de filtro muito longa.")
        if isinstance(value, str) and len(value) > 150:
            raise ValueError("Valor do filtro muito longo.")
        return value

class SortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=36)
    desc: bool = False

class ViewSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    filters: list[FilterSpec] = Field(default_factory=list, max_length=8)
    sort: SortSpec | None = None
    sorts: list[SortSpec] = Field(default_factory=list, max_length=3)
    density: Literal["compact", "comfortable"] = "comfortable"
    pinned: list[str] = Field(default_factory=list, max_length=3)
    columnWidths: dict[str, int] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list, max_length=24)
    page_size: Literal[25, 50, 100] = 50

class CreateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_key: ObjectKey
    name: str = Field(min_length=2, max_length=80)
    scope: Literal["personal"] = "personal"
    config: ViewSpec

class UpdateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)
    config: ViewSpec

def validate_view(object_key: ObjectKey, config: ViewSpec):
    fields = ALLOWED[object_key]
    for f in config.filters:
        kind = fields.get(f.key)
        if kind is None or f.op not in OPS.get(kind, set()):
            raise HTTPException(status_code=422, detail="Filtro incompatível com este objeto.")
        if f.op in {"in", "between"} and (not isinstance(f.value, list) or (f.op == "between" and len(f.value) != 2)):
            raise HTTPException(status_code=422, detail="O operador exige uma lista de valores.")
        if f.op not in {"in", "between"} and isinstance(f.value, list):
            raise HTTPException(status_code=422, detail="O operador não aceita lista.")
        if f.op == "empty" and f.value is not None:
            raise HTTPException(status_code=422, detail="Filtro vazio não recebe valor.")
        if f.op != "empty" and f.value is None:
            raise HTTPException(status_code=422, detail="Informe o valor do filtro.")
        if kind == "number" and f.op not in {"empty", "between"} and (not isinstance(f.value, (float, int)) or isinstance(f.value, bool)):
            raise HTTPException(status_code=422, detail="Filtro numérico exige número.")
    if config.sort and (config.sort.key not in fields or fields[config.sort.key] == "display"):
        raise HTTPException(status_code=422, detail="Ordenação não permitida.")
    sort_keys = [item.key for item in config.sorts]
    if len(sort_keys) != len(set(sort_keys)) or any(key not in fields or fields[key] == "display" for key in sort_keys):
        raise HTTPException(status_code=422, detail="Ordenações incompatíveis com o objeto.")
    if len(set(config.pinned)) != len(config.pinned) or any(key not in fields or key not in config.columns for key in config.pinned):
        raise HTTPException(status_code=422, detail="Colunas fixadas inválidas.")
    if len(config.columnWidths) > 24 or any(key not in config.columns or value < 100 or value > 640 for key, value in config.columnWidths.items()):
        raise HTTPException(status_code=422, detail="Larguras de colunas inválidas.")
    if len(set(config.columns)) != len(config.columns) or any(col not in fields for col in config.columns):
        raise HTTPException(status_code=422, detail="Colunas não permitidas.")

def require_view_access(auth: AuthContext, object_key: ObjectKey):
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Visualizações pessoais exigem sessão de usuário.")
    permission = PERMISSION[object_key]
    if auth.permissions is not None:
        if permission not in auth.permissions:
            raise HTTPException(status_code=403, detail="Permissão insuficiente.")
    elif auth.custom_role_id is not None:
        raise HTTPException(status_code=403, detail="Permissões indisponíveis.")
    elif auth.role == "viewer" and permission not in {"students.view"}:
        raise HTTPException(status_code=403, detail="Permissão insuficiente.")
    elif auth.role == "operator" and permission == "students.sensitive.view":
        raise HTTPException(status_code=403, detail="Permissão insuficiente.")

def serialize(row: ObjectView):
    return {"id": row.id, "object_key": row.object_key, "name": row.name,
            "scope": "personal", "config": row.config, "version": row.config_version,
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}

@router.get("")
async def list_views(object_key: ObjectKey, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    require_view_access(auth, object_key)
    rows = (await db.execute(select(ObjectView).where(
        ObjectView.tenant_id == auth.tenant_id, ObjectView.owner_user_id == auth.user_id,
        ObjectView.object_key == object_key,
    ).order_by(ObjectView.name, ObjectView.id))).scalars().all()
    return {"views": [serialize(row) for row in rows]}

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_view(body: CreateView, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    require_view_access(auth, body.object_key)
    validate_view(body.object_key, body.config)
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Nome inválido.")
    row = ObjectView(tenant_id=auth.tenant_id, owner_user_id=auth.user_id,
                     object_key=body.object_key, name=name, config_version=1,
                     config=body.config.model_dump())
    db.add(row)
    try:
        await db.flush()
        await db.refresh(row)
        payload = serialize(row)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma visualização com esse nome.") from exc
    return payload

async def owner_view(db: AsyncSession, auth: AuthContext, view_id: UUID) -> ObjectView:
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Sessão de usuário necessária.")
    row = (await db.execute(select(ObjectView).where(
        ObjectView.id == str(view_id), ObjectView.tenant_id == auth.tenant_id,
        ObjectView.owner_user_id == auth.user_id,
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Visualização não encontrada.")
    require_view_access(auth, row.object_key)
    return row

@router.put("/{view_id}")
async def update_view(view_id: UUID, body: UpdateView, auth: AuthContext = Depends(get_current_tenant),
                      db: AsyncSession = Depends(get_db)):
    row = await owner_view(db, auth, view_id)
    validate_view(row.object_key, body.config)
    row.name = body.name.strip()
    if len(row.name) < 2:
        raise HTTPException(status_code=422, detail="Nome inválido.")
    row.config = body.config.model_dump()
    try:
        await db.flush()
        await db.refresh(row)
        payload = serialize(row)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma visualização com esse nome.") from exc
    return payload

@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(view_id: UUID, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    row = await owner_view(db, auth, view_id)
    await db.delete(row)
    await db.commit()
