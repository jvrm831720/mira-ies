"""
Schema canônico e utilitários compartilhados pelos conectores.
"""

from __future__ import annotations

from typing import Any, Protocol
from pydantic import BaseModel, Field


CANONICAL_FIELDS = [
    "matricula",
    "nome",
    "curso",
    "turma",
    "semestre",
    "forma_ingresso",
    "telefone",
    "email",
    "dias_atraso_boleto",
    "recorrencia_atrasos",
    "dias_sem_login",
    "presenca_percentual",
    "nota_media",
    "reprovacoes",
]


class CanonicalStudent(BaseModel):
    matricula: str
    nome: str
    curso: str | None = None
    turma: str | None = None
    semestre: int | None = None
    forma_ingresso: str | None = None
    telefone: str | None = None
    email: str | None = None
    dias_atraso_boleto: int | None = None
    recorrencia_atrasos: int | None = None
    dias_sem_login: int | None = None
    presenca_percentual: float | None = None
    nota_media: float | None = None
    reprovacoes: int | None = None
    source_id: str | None = None
    raw: dict[str, Any] | None = None


class ConnectorInfo(BaseModel):
    id: str
    name: str
    category: str
    description: str
    has_api: bool
    endpoints: list[str] = Field(default_factory=list)
    sample_fields: list[str] = Field(default_factory=list)
    docs_url: str | None = None


class Connector(Protocol):
    info: ConnectorInfo

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        ...


def pick(data: dict, *keys: str, default=None):
    for k in keys:
        if k in data and data[k] is not None and data[k] != "":
            return data[k]
        for dk, dv in data.items():
            if str(dk).lower() == k.lower() and dv is not None and dv != "":
                return dv
    return default


def to_int(v, default=None):
    if v is None or v == "":
        return default
    try:
        return int(float(str(v).replace(",", ".")))
    except (ValueError, TypeError):
        return default


def to_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return default


def to_str(v, default=None):
    if v is None:
        return default
    s = str(v).strip()
    return s or default
