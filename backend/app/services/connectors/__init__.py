"""
Conectores de ingestão — ERPs e LMS do mercado PME educacional.

Cada conector normaliza o payload nativo do sistema de origem
para o schema canônico do Beacon (matricula, nome, features de risco...).
"""

from app.services.connectors.registry import (
    CONNECTOR_REGISTRY,
    list_connectors,
    get_connector,
)
from app.services.connectors.pipeline import ingest_records

__all__ = [
    "CONNECTOR_REGISTRY",
    "list_connectors",
    "get_connector",
    "ingest_records",
]
