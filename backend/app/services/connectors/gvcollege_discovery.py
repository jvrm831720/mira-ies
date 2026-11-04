"""Descoberta local e controlada de views sintéticas GVcollege.

Não consulta a API, não infere nomes reais de views e não declara aprovação
institucional. Os identificadores abaixo pertencem somente aos fixtures da MIRA.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class GvcollegeDataClass(StrEnum):
    IDENTIFIER = "identifier"
    PERSONAL = "personal"
    ACADEMIC = "academic"
    FINANCIAL = "financial"
    BEHAVIORAL = "behavioral"


class GvcollegeValueType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class GvcollegeViewField:
    source_field: str
    canonical_field: str
    value_type: GvcollegeValueType
    nullable: bool
    classification: GvcollegeDataClass
    selectable: bool = True


@dataclass(frozen=True)
class GvcollegeSyntheticView:
    view_id: str
    schema_version: str
    fields: tuple[GvcollegeViewField, ...]
    pagination_key: str
    fixture_only: bool = True
    institution_approved: bool = False


SYNTHETIC_GVCOLLEGE_VIEWS: dict[str, GvcollegeSyntheticView] = {
    "synthetic_students_v1": GvcollegeSyntheticView(
        view_id="synthetic_students_v1",
        schema_version="1.0.0",
        pagination_key="matricula",
        fields=(
            GvcollegeViewField("matricula", "matricula", GvcollegeValueType.STRING, False, GvcollegeDataClass.IDENTIFIER),
            GvcollegeViewField("nome", "nome", GvcollegeValueType.STRING, False, GvcollegeDataClass.PERSONAL),
            GvcollegeViewField("curso", "curso", GvcollegeValueType.STRING, True, GvcollegeDataClass.ACADEMIC),
            GvcollegeViewField("campus", "campus", GvcollegeValueType.STRING, True, GvcollegeDataClass.ACADEMIC),
            GvcollegeViewField("semestre", "semestre", GvcollegeValueType.INTEGER, True, GvcollegeDataClass.ACADEMIC),
            GvcollegeViewField("dias_sem_login", "dias_sem_login", GvcollegeValueType.INTEGER, True, GvcollegeDataClass.BEHAVIORAL),
            GvcollegeViewField("presenca_percentual", "presenca_percentual", GvcollegeValueType.NUMBER, True, GvcollegeDataClass.BEHAVIORAL),
            GvcollegeViewField("nota_media", "nota_media", GvcollegeValueType.NUMBER, True, GvcollegeDataClass.ACADEMIC),
        ),
    ),
    "synthetic_financial_v1": GvcollegeSyntheticView(
        view_id="synthetic_financial_v1",
        schema_version="1.0.0",
        pagination_key="matricula",
        fields=(
            GvcollegeViewField("matricula", "matricula", GvcollegeValueType.STRING, False, GvcollegeDataClass.IDENTIFIER),
            GvcollegeViewField("dias_atraso_boleto", "dias_atraso_boleto", GvcollegeValueType.INTEGER, True, GvcollegeDataClass.FINANCIAL),
            GvcollegeViewField("recorrencia_atrasos", "recorrencia_atrasos", GvcollegeValueType.INTEGER, True, GvcollegeDataClass.FINANCIAL),
            GvcollegeViewField("saldo_devedor", "saldo_devedor", GvcollegeValueType.NUMBER, True, GvcollegeDataClass.FINANCIAL),
            GvcollegeViewField("status_financeiro", "status_financeiro", GvcollegeValueType.STRING, True, GvcollegeDataClass.FINANCIAL),
        ),
    ),
}


def discover_synthetic_gvcollege_views() -> list[dict]:
    """Lista somente definições locais explicitamente registradas."""
    return [
        {
            **asdict(view),
            "fields": [asdict(field) for field in view.fields],
            "discovery_mode": "local_static_registry",
            "remote_discovery_performed": False,
        }
        for view in SYNTHETIC_GVCOLLEGE_VIEWS.values()
    ]


def get_synthetic_gvcollege_view(view_id: str) -> GvcollegeSyntheticView:
    try:
        return SYNTHETIC_GVCOLLEGE_VIEWS[view_id]
    except KeyError as exc:
        raise ValueError(f"View sintética não registrada: {view_id}") from exc
