"""Serviço de campos customizados: registry por tenant + validação de valores."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_field import CUSTOM_FIELD_TYPES, CustomFieldDefinition

# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------

def slugify_label(label: str) -> str:
    """"Polo de Apoio Presencial" -> "polo_de_apoio_presencial"."""
    text = unicodedata.normalize("NFKD", label or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return text[:80]


def _parse_number(raw: str) -> float:
    value = raw.strip()
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        value = value.replace(",", ".")
    return float(value)


def _plain(value: str) -> str:
    """Minusculas e sem acentos, para comparar valores de planilha."""
    text = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


_TRUE_VALUES = {"1", "true", "sim", "s", "yes", "verdadeiro", "x"}
_FALSE_VALUES = {"0", "false", "nao", "n", "no", "falso"}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def coerce_value(raw: Any, data_type: str, options: Optional[list] = None):
    """Valida e coage um valor bruto (sempre lido como string) para o tipo do campo.

    Retorna (ok, valor_coagido, mensagem_de_erro). String vazia -> (True, None, None):
    ausência de dado não é erro, apenas não atualiza o campo.
    """
    if raw is None:
        return True, None, None
    text = str(raw).strip()
    if text == "" or text.lower() == "nan":
        return True, None, None
    try:
        if data_type == "text":
            if len(text) > 2000:
                return False, None, "Texto excede 2000 caracteres."
            return True, text, None
        if data_type == "integer":
            number = _parse_number(text)
            if not math.isfinite(number) or not number.is_integer():
                return False, None, f"Valor inteiro inválido: {text!r}"
            return True, int(number), None
        if data_type == "number":
            number = _parse_number(text)
            if not math.isfinite(number):
                return False, None, "Número inválido: valor não finito."
            return True, number, None
        if data_type == "boolean":
            lowered = _plain(text)
            if lowered in _TRUE_VALUES:
                return True, True, None
            if lowered in _FALSE_VALUES:
                return True, False, None
            return False, None, f"Valor booleano inválido: {text!r}"
        if data_type == "date":
            from datetime import datetime
            for fmt in _DATE_FORMATS:
                try:
                    return True, datetime.strptime(text, fmt).date().isoformat(), None
                except ValueError:
                    continue
            return False, None, f"Data inválida: {text!r} (use AAAA-MM-DD ou DD/MM/AAAA)"
        if data_type == "enum":
            allowed = [str(opt) for opt in (options or [])]
            lowered = _plain(text)
            for opt in allowed:
                if _plain(opt) == lowered:
                    return True, opt, None
            return False, None, f"Valor fora das opções permitidas ({', '.join(allowed)}): {text!r}"
        return False, None, f"Tipo desconhecido: {data_type}"
    except (ValueError, OverflowError):
        return False, None, f"Não foi possível converter {text!r} para {data_type}"


# ---------------------------------------------------------------------------
# Persistência (isolada por tenant)
# ---------------------------------------------------------------------------

async def list_definitions(
    db: AsyncSession, tenant_id: str, target: str = "student", active_only: bool = True
) -> list[CustomFieldDefinition]:
    stmt = select(CustomFieldDefinition).where(
        CustomFieldDefinition.tenant_id == tenant_id,
        CustomFieldDefinition.target == target,
    )
    if active_only:
        stmt = stmt.where(CustomFieldDefinition.active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_definition(
    db: AsyncSession, *, tenant_id: str, target: str, name: str, label: str,
    data_type: str, options: Optional[list] = None, required: bool = False,
    is_pii: bool = False, aliases: Optional[list] = None,
) -> CustomFieldDefinition:
    if data_type not in CUSTOM_FIELD_TYPES:
        raise ValueError(f"Tipo inválido. Use: {', '.join(CUSTOM_FIELD_TYPES)}")
    if data_type == "enum" and not options:
        raise ValueError("Campos enum exigem ao menos uma opção.")
    name = slugify_label(name)
    if not name:
        raise ValueError("Nome do campo inválido após normalização.")
    if target != "student":
        raise ValueError("Apenas campos de alunos são suportados nesta versão.")
    from app.services.smart_import import STANDARD_FIELD_TYPES
    if name in STANDARD_FIELD_TYPES:
        raise ValueError("Este nome pertence a um campo padrão da MIRA.")
    conflict = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.tenant_id == tenant_id,
            CustomFieldDefinition.target == target,
            CustomFieldDefinition.name == name,
        )
    )
    if conflict.scalar_one_or_none() is not None:
        raise ValueError(f"Já existe um campo '{name}' para este alvo nesta instituição.")
    definition = CustomFieldDefinition(
        tenant_id=tenant_id, target=target, name=name, label=label,
        data_type=data_type, options=options or None, required=required,
        is_pii=is_pii, aliases=aliases or [],
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition


def build_catalog(definitions: list[CustomFieldDefinition]) -> list[dict[str, Any]]:
    """Catálogo de campos customizados para o motor de mapeamento de importação."""
    catalog = []
    for definition in definitions:
        catalog.append({
            "field": definition.name,
            "label": definition.label,
            "aliases": [definition.label, *(definition.aliases or [])],
            "source": "custom",
            "data_type": definition.data_type,
            "options": definition.options or [],
            "required": definition.required,
            "is_pii": definition.is_pii,
        })
    return catalog
