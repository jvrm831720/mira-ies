"""
Registry central de conectores disponíveis.
"""

from __future__ import annotations

from app.services.connectors.erp import (
    JacadConnector,
    SponteConnector,
    SophiaConnector,
    GvcollegeConnector,
    WpensarConnector,
)
from app.services.connectors.lms import MoodleConnector, CanvasConnector
from app.services.connectors.generic import GenericConnector
from app.services.connectors.base import ConnectorInfo


_jacad = JacadConnector()
_sponte = SponteConnector()
_sophia = SophiaConnector()
_gvcollege = GvcollegeConnector()
_wpensar = WpensarConnector()
_moodle = MoodleConnector()
_canvas = CanvasConnector()
_generic = GenericConnector()

CONNECTOR_REGISTRY: dict[str, object] = {
    "jacad": _jacad,
    "sponte": _sponte,
    "sophia": _sophia,
    "gvcollege": _gvcollege,
    "wpensar": _wpensar,
    "moodle": _moodle,
    "canvas": _canvas,
    "generic": _generic,
}


def get_connector(connector_id: str):
    key = connector_id.lower().strip()
    conn = CONNECTOR_REGISTRY.get(key)
    if not conn:
        raise KeyError(
            f"Conector '{connector_id}' nao encontrado. "
            f"Disponiveis: {', '.join(sorted(set(CONNECTOR_REGISTRY.keys())))}"
        )
    return conn


def list_connectors() -> list[ConnectorInfo]:
    seen = set()
    result = []
    for conn in CONNECTOR_REGISTRY.values():
        info = conn.info  # type: ignore
        if info.id not in seen:
            seen.add(info.id)
            result.append(info)
    return sorted(result, key=lambda x: (x.category, x.name))
