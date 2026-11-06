"""Workspace Object Views: scoped configurations, optimistic concurrency and history.

All requests are authenticated to a real human session; record data is never
persisted in view definitions. PostgreSQL RLS independently checks tenant,
owner and visibility. Config version and revision are separate concepts.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.models.object_view import ObjectView, ObjectViewFavorite, ObjectViewRevision
from app.models.custom_field import CustomFieldDefinition

router = APIRouter(prefix="/object-views", tags=["Object Index / Saved Views"])
ObjectKey = Literal["students", "campaigns", "academic_classes", "academic_programs",
                    "academic_subjects", "academic_teachers", "academic_terms", "collections"]
Scope = Literal["personal", "workspace"]
Op = Literal["eq", "neq", "contains", "not_contains", "starts_with", "gt", "lt",
             "between", "in", "before", "after", "empty"]
ALLOWED = {
    "students": {"nome": "text", "matricula": "text", "curso": "text",
                 "risk_level": "choice", "risk_score": "number", "created_at": "date", "follow_up": "display"},
    "collections": {"external_ref": "text", "status": "choice", "balance": "number",
                    "source": "text", "updated_at": "date"},
    "campaigns": {"title": "text", "status": "choice", "objective": "text",
                  "audience_total": "number", "recommended_channels": "display", "created_at": "date"},
    "academic_classes": {"code": "text", "status": "choice", "subject_id": "text",
                         "term_id": "text", "teacher_id": "text"},
}
for key in ["academic_programs", "academic_subjects", "academic_teachers", "academic_terms"]:
    ALLOWED[key] = {"name": "text", "code": "text", "status": "choice"}

OPS = {
    "text": {"eq", "neq", "contains", "not_contains", "starts_with", "empty"},
    "choice": {"eq", "neq", "in", "empty"},
    "number": {"eq", "gt", "lt", "between", "empty"},
    "date": {"before", "after", "between", "empty"},
}
PERMISSION = {
    "students": "students.view",
    "campaigns": "campaigns.view",
    "academic_classes": "students.sensitive.view",
    "collections": "audit.view",
}
for key in ["academic_programs", "academic_subjects", "academic_teachers", "academic_terms"]:
    PERMISSION[key] = "students.sensitive.view"

SENSITIVE = {"students": frozenset({"risk_level", "risk_score", "follow_up"})}
LABELS = {
    "nome": "Nome", "matricula": "Matrícula", "curso": "Curso",
    "risk_level": "Risco", "risk_score": "Score", "created_at": "Criado em",
    "follow_up": "Acompanhamento", "external_ref": "Referência",
    "status": "Estado", "balance": "Saldo informado", "source": "Origem",
    "updated_at": "Atualização", "title": "Título", "objective": "Objetivo",
    "audience_total": "Público", "recommended_channels": "Canais recomendados",
    "code": "Código", "subject_id": "Disciplina", "term_id": "Período",
    "teacher_id": "Docente", "name": "Nome",
}


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=36)
    op: Op
    value: str | float | list[str | float] | None = None

    @field_validator("value")
    @classmethod
    def valid_value(cls, value):
        if isinstance(value, list) and (
            len(value) > 12 or any(isinstance(item, str) and len(item) > 150 for item in value)
        ):
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
    property_labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("property_labels")
    @classmethod
    def validate_labels(cls, value):
        if len(value) > 24 or any(
            not isinstance(v, str) or len(v.strip()) < 2 or len(v) > 80 for v in value.values()
        ):
            raise ValueError("Rótulos devem ter 2 a 80 caracteres.")
        return value


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
    expected_revision: int = Field(ge=1)


class ShareView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Scope
    expected_revision: int = Field(ge=1)


class DuplicateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)


class RestoreView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    expected_revision: int = Field(ge=1)


def has_permission(auth: AuthContext, permission: str) -> bool:
    if auth.permissions is not None:
        return permission in auth.permissions
    if auth.custom_role_id is not None:
        return False
    if auth.role == "admin":
        return True
    if auth.role == "coordinator":
        return True
    if auth.role == "operator":
        return permission in {"students.view", "campaigns.view"}
    return auth.role == "viewer" and permission == "students.view"


def can_sensitive(auth: AuthContext) -> bool:
    return has_permission(auth, "students.sensitive.view")


def can_share(auth: AuthContext) -> bool:
    # Explicit custom-role entitlement; built-in coordinators/admins only.
    return has_permission(auth, "permissions.manage")


def require_view_access(auth: AuthContext, object_key: ObjectKey):
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Visualizações exigem sessão de usuário.")
    if not has_permission(auth, PERMISSION[object_key]):
        raise HTTPException(status_code=403, detail="Permissão insuficiente.")


def _keys(config: ViewSpec) -> set[str]:
    return (set(config.columns) | set(config.pinned) | set(config.columnWidths)
            | set(config.property_labels) | {item.key for item in config.filters}
            | {item.key for item in config.sorts}
            | ({config.sort.key} if config.sort else set()))


def sensitive_config(object_key: ObjectKey, config: ViewSpec) -> bool:
    return bool(_keys(config) & SENSITIVE.get(object_key, frozenset()))


def validate_view(object_key: ObjectKey, config: ViewSpec):
    fields = ALLOWED[object_key]
    for f in config.filters:
        kind = fields.get(f.key)
        if kind is None or f.op not in OPS.get(kind, set()):
            raise HTTPException(status_code=422, detail="Filtro incompatível com este objeto.")
        if f.op in {"in", "between"} and (
            not isinstance(f.value, list) or not f.value or (f.op == "between" and len(f.value) != 2)
        ):
            raise HTTPException(status_code=422, detail="O operador exige uma lista de valores.")
        if f.op not in {"in", "between"} and isinstance(f.value, list):
            raise HTTPException(status_code=422, detail="O operador não aceita lista.")
        if f.op == "empty" and f.value is not None:
            raise HTTPException(status_code=422, detail="Filtro vazio não recebe valor.")
        if f.op != "empty" and f.value is None:
            raise HTTPException(status_code=422, detail="Informe o valor do filtro.")
        if kind == "number" and f.op not in {"empty", "between"} and (
            not isinstance(f.value, (float, int)) or isinstance(f.value, bool)
        ):
            raise HTTPException(status_code=422, detail="Filtro numérico exige número.")
    if config.sort and (config.sort.key not in fields or fields[config.sort.key] == "display"):
        raise HTTPException(status_code=422, detail="Ordenação não permitida.")
    sort_keys = [item.key for item in config.sorts]
    if len(sort_keys) != len(set(sort_keys)) or any(
        key not in fields or fields[key] == "display" for key in sort_keys
    ):
        raise HTTPException(status_code=422, detail="Ordenações incompatíveis com o objeto.")
    if len(set(config.pinned)) != len(config.pinned) or any(
        key not in fields or key not in config.columns for key in config.pinned
    ):
        raise HTTPException(status_code=422, detail="Colunas fixadas inválidas.")
    if len(config.columnWidths) > 24 or any(
        key not in config.columns or value < 100 or value > 640
        for key, value in config.columnWidths.items()
    ):
        raise HTTPException(status_code=422, detail="Larguras de colunas inválidas.")
    if len(set(config.columns)) != len(config.columns) or any(col not in fields for col in config.columns):
        raise HTTPException(status_code=422, detail="Colunas não permitidas.")
    if any(key not in fields or key not in config.columns for key in config.property_labels):
        raise HTTPException(status_code=422, detail="Rótulo para propriedade não autorizada.")


def _view_config(row: ObjectView) -> tuple[dict | None, str]:
    if row.config_version != 1 or not isinstance(row.config, dict):
        return None, "unsupported"
    try:
        parsed = ViewSpec.model_validate(row.config)
        validate_view(row.object_key, parsed)
        normalized = parsed.model_dump()
        return normalized, "current" if normalized == row.config else "upgraded"
    except (ValidationError, HTTPException, KeyError, TypeError):
        return None, "unsupported"


async def _sensitivity_context(auth: AuthContext, db: AsyncSession):
    await db.execute(text("SELECT set_config('app.view_sensitive', :value, true)"),
                     {"value": "1" if can_sensitive(auth) else "0"})


def _assert_sensitive(auth: AuthContext, object_key: ObjectKey, config: ViewSpec):
    if sensitive_config(object_key, config) and not can_sensitive(auth):
        raise HTTPException(status_code=403, detail="Configuração exige acesso aos campos sensíveis.")


def _name(value: str) -> str:
    result = value.strip()
    if len(result) < 2:
        raise HTTPException(status_code=422, detail="Nome inválido.")
    return result


def _serialize(row: ObjectView, auth: AuthContext, favorite: bool = False):
    config, schema_status = _view_config(row)
    owner = row.owner_user_id == auth.user_id
    if row.is_sensitive and not can_sensitive(auth):
        raise HTTPException(status_code=403, detail="Visualização restrita.")
    return {
        "id": row.id, "object_key": row.object_key, "name": row.name,
        "scope": row.scope, "owner_user_id": row.owner_user_id,
        "config": config, "schema_status": schema_status,
        "version": row.config_version, "revision": row.revision,
        "favorite": favorite, "can_edit": owner, "can_share": owner and can_share(auth),
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def serialize(row: ObjectView):
    """Legacy serializer used only by old helper consumers, never for permission checks."""
    return {
        "id": row.id, "object_key": row.object_key, "name": row.name,
        "scope": row.scope, "config": row.config, "version": row.config_version,
        "revision": row.revision,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


async def _accessible_view(db: AsyncSession, auth: AuthContext, view_id: UUID) -> ObjectView:
    await _sensitivity_context(auth, db)
    row = (await db.execute(select(ObjectView).where(
        ObjectView.id == str(view_id), ObjectView.tenant_id == auth.tenant_id,
        or_(ObjectView.owner_user_id == auth.user_id, ObjectView.scope == "workspace"),
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Visualização não encontrada.")
    require_view_access(auth, row.object_key)
    if row.is_sensitive and not can_sensitive(auth):
        raise HTTPException(status_code=404, detail="Visualização não encontrada.")
    return row


async def owner_view(db: AsyncSession, auth: AuthContext, view_id: UUID) -> ObjectView:
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Sessão de usuário necessária.")
    await _sensitivity_context(auth, db)
    row = (await db.execute(select(ObjectView).where(
        ObjectView.id == str(view_id), ObjectView.tenant_id == auth.tenant_id,
        ObjectView.owner_user_id == auth.user_id,
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Visualização não encontrada.")
    require_view_access(auth, row.object_key)
    if row.is_sensitive and not can_sensitive(auth):
        raise HTTPException(status_code=403, detail="Campos sensíveis indisponíveis.")
    return row


def _version_guard(row: ObjectView, expected: int):
    if row.revision != expected:
        raise HTTPException(status_code=409, detail={
            "code": "VIEW_REVISION_CONFLICT", "current_revision": row.revision,
            "message": "A visualização mudou. Atualize antes de salvar.",
        })


def _snapshot(row: ObjectView, editor_id: str) -> ObjectViewRevision:
    return ObjectViewRevision(
        tenant_id=row.tenant_id, view_id=row.id, edited_by_user_id=editor_id,
        revision=row.revision, name=row.name, scope=row.scope,
        config_version=row.config_version, config=row.config,
        is_sensitive=row.is_sensitive,
    )


async def _persist(db: AsyncSession, row: ObjectView, editor_id: str):
    try:
        await db.flush()
        db.add(_snapshot(row, editor_id))
        await db.flush()
        await db.refresh(row)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Nome ou revisão já utilizados.") from exc


@router.get("/metadata")
async def object_metadata(
    object_key: ObjectKey, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    require_view_access(auth, object_key)
    sensitive = can_sensitive(auth)
    custom = []
    if object_key == "students" and has_permission(auth, "data.view"):
        definitions = (await db.execute(select(CustomFieldDefinition).where(
            CustomFieldDefinition.tenant_id == auth.tenant_id,
            CustomFieldDefinition.target == "student",
            CustomFieldDefinition.active.is_(True),
        ).order_by(CustomFieldDefinition.label))).scalars().all()
        custom = [{
            "key": "custom." + item.name, "label": item.label,
            "type": item.data_type, "source": "existing_registry",
            "sensitive": item.is_pii, "filterable": False, "sortable": False,
            "view_enabled": False,
            "reason": "Catálogo disponível, mas a API do índice ainda não oferece consulta remota para este campo.",
        } for item in definitions if sensitive or not item.is_pii]
    return {
        "custom_properties": custom,
        "object_key": object_key, "schema_version": 1, "property_source": "object-index",
        "fields": [{
            "key": key, "label": LABELS.get(key, key), "type": kind,
            "sensitive": key in SENSITIVE.get(object_key, frozenset()),
            "filterable": kind in OPS, "sortable": kind != "display",
            "operators": sorted(OPS.get(kind, set())),
        } for key, kind in ALLOWED[object_key].items()
            if sensitive or key not in SENSITIVE.get(object_key, frozenset())],
        "notes": "Campos personalizados existentes são geridos pelo registry /custom-fields. "
                 "Não são automaticamente filtráveis no Object Index.",
    }


@router.get("")
async def list_views(
    object_key: ObjectKey, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    require_view_access(auth, object_key)
    await _sensitivity_context(auth, db)
    criteria = [
        ObjectView.tenant_id == auth.tenant_id,
        ObjectView.object_key == object_key,
        or_(ObjectView.owner_user_id == auth.user_id, ObjectView.scope == "workspace"),
    ]
    if not can_sensitive(auth):
        criteria.append(ObjectView.is_sensitive.is_(False))
    rows = (await db.execute(select(ObjectView).where(*criteria)
                             .order_by(ObjectView.scope, ObjectView.name, ObjectView.id))).scalars().all()
    favorites = (await db.execute(select(ObjectViewFavorite.view_id).where(
        ObjectViewFavorite.tenant_id == auth.tenant_id,
        ObjectViewFavorite.user_id == auth.user_id,
    ))).scalars().all()
    favs = set(favorites)
    return {"views": [_serialize(row, auth, row.id in favs) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_view(
    body: CreateView, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    require_view_access(auth, body.object_key)
    validate_view(body.object_key, body.config)
    _assert_sensitive(auth, body.object_key, body.config)
    await _sensitivity_context(auth, db)
    row = ObjectView(
        tenant_id=auth.tenant_id, owner_user_id=auth.user_id,
        object_key=body.object_key, name=_name(body.name), scope="personal",
        revision=1, config_version=1, config=body.config.model_dump(),
        is_sensitive=sensitive_config(body.object_key, body.config),
    )
    db.add(row)
    await _persist(db, row, auth.user_id)
    return _serialize(row, auth)


@router.get("/{view_id}")
async def get_view(
    view_id: UUID, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await _accessible_view(db, auth, view_id)
    favorite = await db.get(ObjectViewFavorite, (auth.tenant_id, auth.user_id, row.id))
    return _serialize(row, auth, favorite is not None)


@router.put("/{view_id}")
async def update_view(
    view_id: UUID, body: UpdateView, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await owner_view(db, auth, view_id)
    _version_guard(row, body.expected_revision)
    validate_view(row.object_key, body.config)
    _assert_sensitive(auth, row.object_key, body.config)
    row.name = _name(body.name)
    row.config = body.config.model_dump()
    row.is_sensitive = sensitive_config(row.object_key, body.config)
    row.revision += 1
    await _persist(db, row, auth.user_id)
    return _serialize(row, auth)


@router.post("/{view_id}/share")
async def share_view(
    view_id: UUID, body: ShareView, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await owner_view(db, auth, view_id)
    _version_guard(row, body.expected_revision)
    if not can_share(auth):
        raise HTTPException(status_code=403, detail="Compartilhamento exige permissão de gerenciamento.")
    config, state = _view_config(row)
    if state == "unsupported" or config is None:
        raise HTTPException(status_code=409, detail="Converta a configuração antes de compartilhar.")
    row.scope = body.scope
    row.revision += 1
    await _persist(db, row, auth.user_id)
    return _serialize(row, auth)


@router.post("/{view_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_view(
    view_id: UUID, body: DuplicateView, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    origin = await _accessible_view(db, auth, view_id)
    config, state = _view_config(origin)
    if state == "unsupported" or config is None:
        raise HTTPException(status_code=409, detail="Versão da visualização não suportada.")
    validated = ViewSpec.model_validate(config)
    _assert_sensitive(auth, origin.object_key, validated)
    copy = ObjectView(
        tenant_id=auth.tenant_id, owner_user_id=auth.user_id,
        object_key=origin.object_key, name=_name(body.name), scope="personal",
        revision=1, config_version=1, config=config,
        is_sensitive=sensitive_config(origin.object_key, validated),
    )
    db.add(copy)
    await _persist(db, copy, auth.user_id)
    return _serialize(copy, auth)


@router.get("/{view_id}/revisions")
async def list_revisions(
    view_id: UUID, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await owner_view(db, auth, view_id)
    history = (await db.execute(select(ObjectViewRevision).where(
        ObjectViewRevision.tenant_id == auth.tenant_id,
        ObjectViewRevision.view_id == row.id,
    ).order_by(ObjectViewRevision.revision.desc()).limit(50))).scalars().all()
    await db.rollback()  # release FOR UPDATE before the history is shown
    return {"revisions": [{
        "revision": item.revision, "name": item.name, "scope": item.scope,
        "schema_version": item.config_version, "created_at": item.created_at.isoformat(),
    } for item in history]}


@router.post("/{view_id}/restore")
async def restore_view(
    view_id: UUID, body: RestoreView, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await owner_view(db, auth, view_id)
    _version_guard(row, body.expected_revision)
    prior = (await db.execute(select(ObjectViewRevision).where(
        ObjectViewRevision.tenant_id == auth.tenant_id,
        ObjectViewRevision.view_id == row.id,
        ObjectViewRevision.revision == body.revision,
    ))).scalar_one_or_none()
    if prior is None or prior.config_version != 1:
        raise HTTPException(status_code=404, detail="Revisão indisponível.")
    try:
        config = ViewSpec.model_validate(prior.config)
        validate_view(row.object_key, config)
    except (ValidationError, HTTPException) as exc:
        raise HTTPException(status_code=409, detail="Revisão incompatível com o catálogo atual.") from exc
    _assert_sensitive(auth, row.object_key, config)
    if prior.scope == "workspace" and not can_share(auth):
        raise HTTPException(status_code=403, detail="Restauração compartilhada não autorizada.")
    row.name = prior.name
    row.scope = prior.scope
    row.config_version = 1
    row.config = config.model_dump()
    row.is_sensitive = sensitive_config(row.object_key, config)
    row.revision += 1
    await _persist(db, row, auth.user_id)
    return _serialize(row, auth)


@router.put("/{view_id}/favorite")
async def favorite_view(
    view_id: UUID, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await _accessible_view(db, auth, view_id)
    existing = await db.get(ObjectViewFavorite, (auth.tenant_id, auth.user_id, row.id))
    if existing is None:
        db.add(ObjectViewFavorite(tenant_id=auth.tenant_id, user_id=auth.user_id, view_id=row.id))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()  # concurrent favorite; idempotent result
    return {"favorite": True}


@router.delete("/{view_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def unfavorite_view(
    view_id: UUID, auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await _accessible_view(db, auth, view_id)
    existing = await db.get(ObjectViewFavorite, (auth.tenant_id, auth.user_id, row.id))
    if existing is not None:
        await db.delete(existing)
        await db.commit()


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    view_id: UUID, expected_revision: int = Query(ge=1),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    row = await owner_view(db, auth, view_id)
    _version_guard(row, expected_revision)
    await db.delete(row)
    await db.commit()
