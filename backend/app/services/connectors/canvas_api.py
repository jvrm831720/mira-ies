"""Read-only Canvas LMS REST API client.

This client exposes a narrow GET-only allowlist. It does not persist data,
mutate Canvas resources, or follow pagination links outside the configured
Canvas origin and /api/v1 namespace.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx


class CanvasApiError(RuntimeError):
    """Base error for Canvas API failures."""


class CanvasAuthenticationError(CanvasApiError):
    """Canvas rejected the access token or its permissions."""


class CanvasContractError(CanvasApiError):
    """Canvas returned an invalid or unexpected response."""


@dataclass(frozen=True)
class CanvasConfig:
    base_url: str
    access_token: str
    timeout_seconds: float = 30.0

    def api_base_url(self) -> str:
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
            raise ValueError("Canvas base_url deve ser HTTPS e não pode conter credenciais, query ou fragmento.")
        if not self.access_token or not self.access_token.strip():
            raise ValueError("Token Canvas obrigatório.")
        if len(self.access_token) > 4096:
            raise ValueError("Token Canvas excede o limite permitido.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Timeout deve ser positivo e finito.")
        return self.base_url.strip().rstrip("/") + "/api/v1/"


_ALLOWED_PATHS = (
    re.compile(r"^courses$"),
    re.compile(r"^courses/[1-9][0-9]*/users$"),
    re.compile(r"^courses/[1-9][0-9]*/enrollments$"),
    re.compile(r"^courses/[1-9][0-9]*/assignments$"),
    re.compile(r"^courses/[1-9][0-9]*/assignments/[1-9][0-9]*/submissions$"),
    re.compile(r"^users/[1-9][0-9]*/missing_submissions$"),
)


class CanvasApiClient:
    """Minimal GET-only client for documented Canvas REST resources."""

    def __init__(
        self,
        config: CanvasConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._api_base = config.api_base_url()
        self._origin = (urlsplit(self._api_base).scheme, urlsplit(self._api_base).netloc)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {config.access_token}",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CanvasApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @staticmethod
    def _validate_path(path: str) -> str:
        normalized = path.strip("/")
        if not any(pattern.fullmatch(normalized) for pattern in _ALLOWED_PATHS):
            raise ValueError("Endpoint Canvas não permitido pelo cliente read-only.")
        return normalized

    def _validate_page_url(self, url: str) -> None:
        parsed = urlsplit(url)
        api_path = urlsplit(self._api_base).path
        relative_path = parsed.path[len(api_path):] if parsed.path.startswith(api_path) else ""
        if (
            (parsed.scheme, parsed.netloc) != self._origin
            or not relative_path
            or not any(pattern.fullmatch(relative_path) for pattern in _ALLOWED_PATHS)
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise CanvasContractError("Canvas retornou link de paginação fora da origem/API permitida.")

    async def _get_url(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        self._validate_page_url(url)
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise CanvasApiError(f"Falha de transporte Canvas ({type(exc).__name__}).") from exc
        if response.status_code in {401, 403}:
            raise CanvasAuthenticationError("Token Canvas inválido ou sem permissão para a consulta.")
        if response.status_code >= 500:
            raise CanvasApiError(f"Canvas indisponível (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise CanvasApiError(f"Canvas rejeitou a consulta (HTTP {response.status_code}).")
        return response

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        normalized = self._validate_path(path)
        response = await self._get_url(urljoin(self._api_base, normalized), params)
        try:
            return response.json()
        except ValueError as exc:
            raise CanvasContractError("Canvas retornou JSON inválido.") from exc

    async def get_all(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int = 10,
    ) -> list[Any]:
        """Fetch bounded pages; only follow same-origin /api/v1 Link URLs."""
        normalized = self._validate_path(path)
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 100:
            raise ValueError("max_pages deve ser um inteiro entre 1 e 100.")
        url = urljoin(self._api_base, normalized)
        page_params = params
        results: list[Any] = []
        for _ in range(max_pages):
            response = await self._get_url(url, page_params)
            try:
                payload = response.json()
            except ValueError as exc:
                raise CanvasContractError("Canvas retornou JSON inválido.") from exc
            if not isinstance(payload, list):
                raise CanvasContractError("Paginação Canvas esperava uma lista JSON.")
            results.extend(payload)
            next_url = response.links.get("next", {}).get("url")
            if not next_url:
                return results
            resolved = urljoin(str(response.url), next_url)
            self._validate_page_url(resolved)
            url = resolved
            page_params = None
        return results

    async def list_courses(self, params: dict[str, Any] | None = None) -> Any:
        return await self.get("courses", params)

    async def list_course_users(self, course_id: int, params: dict[str, Any] | None = None) -> Any:
        return await self.get(f"courses/{self._id(course_id)}/users", params)

    async def list_course_enrollments(self, course_id: int, params: dict[str, Any] | None = None) -> Any:
        return await self.get(f"courses/{self._id(course_id)}/enrollments", params)

    async def list_course_assignments(self, course_id: int, params: dict[str, Any] | None = None) -> Any:
        return await self.get(f"courses/{self._id(course_id)}/assignments", params)

    async def list_assignment_submissions(
        self, course_id: int, assignment_id: int, params: dict[str, Any] | None = None
    ) -> Any:
        return await self.get(
            f"courses/{self._id(course_id)}/assignments/{self._id(assignment_id)}/submissions",
            params,
        )

    async def list_missing_submissions(
        self, user_id: int, params: dict[str, Any] | None = None
    ) -> Any:
        return await self.get(f"users/{self._id(user_id)}/missing_submissions", params)

    @staticmethod
    def _id(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("Identificador Canvas deve ser um inteiro positivo.")
        return value
