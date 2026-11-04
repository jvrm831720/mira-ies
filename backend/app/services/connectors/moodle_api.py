"""Read-only Moodle Web Services REST client.

The enabled functions are site-specific. This client deliberately exposes only
an allowlist of documented read operations and sends tokens in the POST body.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import math
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.connectors.tenant_destinations import (
    _destination_authorization_token,
    authorize_tenant_destination,
    require_destination_authorization,
)


MOODLE_READ_FUNCTIONS = frozenset({
    "core_webservice_get_site_info",
    "core_user_get_users_by_field",
    "core_enrol_get_users_courses",
    "core_completion_get_activities_completion_status",
})


class MoodleApiError(RuntimeError):
    """Base error for Moodle Web Services failures."""


class MoodleAuthenticationError(MoodleApiError):
    """Moodle rejected the configured token or its permissions."""


class MoodleFunctionUnavailableError(MoodleApiError):
    """The institution has not enabled the requested external function."""


class MoodleContractError(MoodleApiError):
    """Moodle returned an invalid or unexpected response."""


@dataclass(frozen=True)
class MoodleConfig:
    base_url: str
    token: str = field(repr=False)
    timeout_seconds: float = 30.0

    def endpoint_url(self) -> str:
        parsed = urlsplit(self.base_url.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(part in {".", ".."} for part in parsed.path.split("/"))
        ):
            raise ValueError("Moodle base_url deve ser HTTPS e não pode conter credenciais, query ou fragmento.")
        if not self.token or not self.token.strip():
            raise ValueError("Token Moodle obrigatório.")
        if len(self.token) > 4096:
            raise ValueError("Token Moodle excede o limite permitido.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Timeout deve ser positivo e finito.")
        path = parsed.path.rstrip("/") + "/webservice/rest/server.php"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _flatten_params(value: Any, prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key or "[" in key or "]" in key:
                raise ValueError("Nome de parâmetro Moodle inválido.")
            child_prefix = f"{prefix}[{key}]" if prefix else key
            flattened.update(_flatten_params(child, child_prefix))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            flattened.update(_flatten_params(child, child_prefix))
    elif isinstance(value, bool):
        flattened[prefix] = "1" if value else "0"
    elif isinstance(value, (str, int, float)):
        flattened[prefix] = str(value)
    else:
        raise ValueError(f"Tipo de parâmetro Moodle não suportado: {prefix or 'root'}.")
    return flattened


class MoodleApiClient:
    """Minimal read-only client for Moodle's standard REST web service endpoint."""

    @classmethod
    async def for_tenant(
        cls,
        db: AsyncSession,
        *,
        tenant_id: str,
        config: MoodleConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "MoodleApiClient":
        """Build only after the tenant's persisted Moodle destination is approved."""
        approved = await authorize_tenant_destination(
            db, tenant_id=tenant_id, connector_key="moodle", url=config.base_url
        )
                return cls(replace(config, base_url=approved), transport=transport, _destination_authorization=_destination_authorization_token())

    def __init__(
        self,
        config: MoodleConfig,
        *,
        _destination_authorization: object | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        require_destination_authorization(_destination_authorization)
        self.config = config
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json"},
        )
        self._endpoint = config.endpoint_url()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MoodleApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def call(self, function: str, params: Mapping[str, Any] | None = None) -> Any:
        if function not in MOODLE_READ_FUNCTIONS:
            raise ValueError("Função Moodle não permitida pelo cliente read-only.")
        supplied = dict(params or {})
        reserved = {"wstoken", "wsfunction", "moodlewsrestformat"}
        if reserved.intersection(supplied):
            raise ValueError("Parâmetros de autenticação/protocolo são gerenciados pelo cliente.")

        form = {
            "wstoken": self.config.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        form.update(_flatten_params(supplied))
        try:
            response = await self._client.post(self._endpoint, data=form)
        except httpx.HTTPError as exc:
            raise MoodleApiError(f"Falha de transporte Moodle ({type(exc).__name__}).") from exc

        if response.status_code in {401, 403}:
            raise MoodleAuthenticationError("Token Moodle inválido ou sem permissão.")
        if response.status_code >= 500:
            raise MoodleApiError(f"Moodle indisponível (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise MoodleApiError(f"Moodle rejeitou a consulta (HTTP {response.status_code}).")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MoodleContractError("Moodle retornou JSON inválido.") from exc

        if isinstance(payload, dict) and payload.get("exception"):
            error_code = payload.get("errorcode")
            if error_code == "invalidtoken":
                raise MoodleAuthenticationError("Token Moodle inválido ou expirado.")
            if error_code == "functionnotavailable":
                raise MoodleFunctionUnavailableError(
                    f"Função Moodle não habilitada no serviço externo: {function}."
                )
            raise MoodleApiError(f"Moodle retornou erro de serviço ({error_code or 'unknown'}).")
        return payload

    async def get_site_info(self) -> dict[str, Any]:
        result = await self.call("core_webservice_get_site_info")
        if not isinstance(result, dict):
            raise MoodleContractError("Informações do site Moodle devem ser um objeto JSON.")
        return result

    async def get_users_by_field(self, field: str, values: list[str]) -> list[dict[str, Any]]:
        if field not in {"id", "username", "idnumber", "email"}:
            raise ValueError("Campo de busca de usuário Moodle não permitido.")
        if not values or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Informe ao menos um identificador de usuário válido.")
        result = await self.call(
            "core_user_get_users_by_field",
            {"field": field, "values": values},
        )
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise MoodleContractError("Consulta Moodle de usuários retornou formato inválido.")
        return result

    async def get_user_courses(self, user_id: int) -> list[dict[str, Any]]:
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
            raise ValueError("user_id deve ser um inteiro positivo.")
        result = await self.call("core_enrol_get_users_courses", {"userid": user_id})
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise MoodleContractError("Consulta Moodle de cursos retornou formato inválido.")
        return result

    async def get_activity_completion(self, course_id: int, user_id: int) -> dict[str, Any]:
        for name, value in (("course_id", course_id), ("user_id", user_id)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} deve ser um inteiro positivo.")
        result = await self.call(
            "core_completion_get_activities_completion_status",
            {"courseid": course_id, "userid": user_id},
        )
        if not isinstance(result, dict):
            raise MoodleContractError("Consulta Moodle de conclusão retornou formato inválido.")
        return result
