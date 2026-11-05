"""API de campos customizados (registry por tenant)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.custom_field import CUSTOM_FIELD_TYPES
from app.services import custom_fields as service

router = APIRouter()


class CustomFieldCreate(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    name: str | None = Field(default=None, max_length=80)  # opcional; deriva do label
    target: str = Field(default="student", pattern="^student$")
    data_type: str = Field(max_length=20)
    options: list[str] | None = None
    required: bool = False
    is_pii: bool = False
    aliases: list[str] = Field(default_factory=list)


class CustomFieldUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=120)
    options: list[str] | None = None
    required: bool | None = None
    is_pii: bool | None = None
    aliases: list[str] | None = None
    active: bool | None = None


def _serialize(definition):
    return {
        "id": definition.id, "target": definition.target, "name": definition.name,
        "label": definition.label, "data_type": definition.data_type,
        "options": definition.options or [], "required": definition.required,
        "is_pii": definition.is_pii, "aliases": definition.aliases or [],
        "active": definition.active, "created_at": definition.created_at,
        "updated_at": definition.updated_at,
    }


@router.get("/custom-fields")
async def list_custom_fields(
    target: str = Query("student", max_length=50),
    include_inactive: bool = Query(False),
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    definitions = await service.list_definitions(
        db, auth.tenant_id, target=target, active_only=not include_inactive
    )
    return {"items": [_serialize(d) for d in definitions], "types": list(CUSTOM_FIELD_TYPES)}


@router.post("/custom-fields", status_code=201)
async def create_custom_field(
    body: CustomFieldCreate,
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    try:
        definition = await service.create_definition(
            db, tenant_id=auth.tenant_id, target=body.target,
            name=body.name or body.label, label=body.label, data_type=body.data_type,
            options=body.options, required=body.required, is_pii=body.is_pii,
            aliases=body.aliases,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(definition)


@router.patch("/custom-fields/{definition_id}")
async def update_custom_field(
    definition_id: str,
    body: CustomFieldUpdate,
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.custom_field import CustomFieldDefinition

    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == definition_id,
            CustomFieldDefinition.tenant_id == auth.tenant_id,
        )
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise HTTPException(status_code=404, detail="Campo customizado não encontrado")
    if body.label is not None:
        definition.label = body.label
    if body.options is not None:
        if definition.data_type == "enum" and not body.options:
            raise HTTPException(status_code=422, detail="Campo enum precisa ter opções.")
        definition.options = body.options
    if body.required is not None:
        definition.required = body.required
    if body.is_pii is not None:
        definition.is_pii = body.is_pii
    if body.aliases is not None:
        definition.aliases = body.aliases
    if body.active is not None:
        definition.active = body.active
    await db.flush()
    await db.refresh(definition)
    await db.commit()
    return _serialize(definition)


@router.delete("/custom-fields/{definition_id}", status_code=204)
async def delete_custom_field(
    definition_id: str,
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    """Exclui a definição apenas se nenhum aluno tiver valor no campo;
    caso contrário desative via PATCH {active: false}."""
    from sqlalchemy import func, select
    from app.models.custom_field import CustomFieldDefinition
    from app.models.student import Student

    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == definition_id,
            CustomFieldDefinition.tenant_id == auth.tenant_id,
        )
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise HTTPException(status_code=404, detail="Campo customizado não encontrado")
    usage = await db.execute(
        select(func.count(Student.id)).where(
            Student.tenant_id == auth.tenant_id,
            Student.custom_fields.has_key(definition.name),
        )
    )
    if usage.scalar() > 0:
        raise HTTPException(
            status_code=409,
            detail="Campo em uso por alunos; desative-o (PATCH active=false) em vez de excluir.",
        )
    await db.delete(definition)
    await db.commit()
