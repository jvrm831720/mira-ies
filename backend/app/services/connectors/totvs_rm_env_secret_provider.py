"""Environment-secret resolver for one institution/coligada RM connection.

In production, populate these values through the worker platform's secret manager.
The values are read only when a job is claimed and are never persisted or logged.
"""
from __future__ import annotations

import os
import re


def _key_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", value).upper()
    if not normalized:
        raise ValueError("Identificador de conexão vazio.")
    return normalized


def resolve_rm_connection(*, tenant_id: str, coligada_id: str, source_name: str) -> dict:
    del source_name  # Source selection is enforced by the executor's allowlisted contract.
    prefix = f"RM_CONN_{_key_part(tenant_id)}_{_key_part(coligada_id)}"
    required = ("BASE_URL", "USERNAME", "PASSWORD")
    values = {name: os.environ.get(f"{prefix}_{name}", "") for name in required}
    if any(not value for value in values.values()):
        raise RuntimeError("Segredos da conexão RM não configurados para tenant/coligada.")
    context = {"CODCOLIGADA": coligada_id}
    for field in ("CODFILIAL", "CODTIPOCURSO", "CODSISTEMA"):
        value = os.environ.get(f"{prefix}_{field}")
        if value:
            context[field] = value
    return {
        "base_url": values["BASE_URL"],
        "username": values["USERNAME"],
        "password": values["PASSWORD"],
        "context_headers": context,
    }
