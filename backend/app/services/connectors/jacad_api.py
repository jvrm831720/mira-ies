"""Read-only JACAD REST client. Credentials are never logged or returned."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class JacadConnectionError(RuntimeError):
    pass


def validate_jacad_base_url(value: str) -> str:
    parsed = urlsplit((value or "").strip().rstrip("/"))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("Informe uma URL HTTPS válida do ambiente JACAD.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Endereço IP não é aceito como host JACAD.")
    if not (host == "jacad.com.br" or host.endswith(".jacad.com.br")):
        raise ValueError("O host deve pertencer ao domínio oficial *.jacad.com.br.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Informe somente a origem do ambiente, sem caminho ou parâmetros.")
    return f"https://{host}" + (f":{parsed.port}" if parsed.port else "")


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if not secret:
        raise RuntimeError("SECRET_KEY segura é obrigatória para armazenar credenciais de integração.")
    digest = hashlib.sha256(("mira:jacad-credential:v1:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_api_token(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise JacadConnectionError("Não foi possível descriptografar a credencial JACAD.") from exc


class JacadApiClient:
    def __init__(self, base_url: str, api_token: str, *, timeout: float = 25.0, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = validate_jacad_base_url(base_url)
        if not api_token or len(api_token) > 40:
            raise ValueError("O token de acesso JACAD deve ter entre 1 e 40 caracteres.")
        self.api_token = api_token
        self.timeout = timeout
        self._jwt: str | None = None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            headers={"Accept": "application/json"},
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def authenticate(self, *, force: bool = False) -> str:
        if self._jwt and not force:
            return self._jwt
        try:
            response = await self._client.post("/api/v1/auth/token", headers={"token": self.api_token})
        except httpx.HTTPError as exc:
            raise JacadConnectionError("Falha de rede ao autenticar no JACAD.") from exc
        if response.status_code != 200:
            raise JacadConnectionError(self._safe_error(response.status_code))
        try:
            payload = response.json()
        except ValueError as exc:
            raise JacadConnectionError("Resposta de autenticação JACAD não é JSON válido.") from exc
        jwt = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(jwt, str) or not jwt:
            raise JacadConnectionError("JACAD não retornou um token de sessão válido.")
        self._jwt = jwt
        return jwt

    @staticmethod
    def _safe_error(status_code: int) -> str:
        messages = {
            401: "Credencial JACAD inválida ou expirada.",
            403: "O token JACAD não tem permissão para este recurso.",
            404: "Endpoint não encontrado no ambiente JACAD configurado.",
            429: "Limite de requisições JACAD atingido. Tente novamente mais tarde.",
        }
        return messages.get(status_code, f"JACAD retornou HTTP {status_code}.")

    async def get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(2):
            jwt = await self.authenticate(force=attempt == 1)
            try:
                response = await self._client.get(
                    path, params=params, headers={"Authorization": f"Bearer {jwt}"}
                )
            except httpx.HTTPError as exc:
                raise JacadConnectionError("Falha de rede durante consulta ao JACAD.") from exc
            if response.status_code == 401 and attempt == 0:
                self._jwt = None
                continue
            if response.status_code != 200:
                raise JacadConnectionError(self._safe_error(response.status_code))
            try:
                payload = response.json()
            except ValueError as exc:
                raise JacadConnectionError("Resposta JACAD não é JSON válido.") from exc
            if not isinstance(payload, dict):
                raise JacadConnectionError("Formato inesperado na resposta JACAD.")
            return payload
        raise JacadConnectionError("Não foi possível renovar a sessão JACAD.")

    async def test_connection(self) -> dict:
        payload = await self.get("/api/v2/academico/alunos", {"pageSize": 1})
        elements = payload.get("elements")
        if not isinstance(elements, list):
            raise JacadConnectionError("A API respondeu, mas não retornou a lista de alunos esperada.")
        return {"authenticated": True, "students_endpoint": True, "sample_records": len(elements)}

    async def fetch_students(self, *, page_size: int = 5000, max_pages: int = 200) -> list[dict]:
        page_size = min(max(int(page_size), 1), 5000)
        cursor: int | str | None = None
        seen_cursors: set[str] = set()
        records: list[dict] = []
        for _ in range(max_pages):
            params: dict[str, int | str] = {"pageSize": page_size}
            if cursor is not None:
                params["idCursor"] = cursor
            payload = await self.get("/api/v2/academico/alunos", params)
            elements = payload.get("elements")
            if not isinstance(elements, list):
                raise JacadConnectionError("Resposta de alunos sem a lista 'elements'.")
            records.extend(item for item in elements if isinstance(item, dict))
            page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
            next_cursor = page.get("idCursorProximo")
            if not elements or next_cursor in (None, "", 0, "0"):
                return records
            marker = str(next_cursor)
            if marker in seen_cursors or marker == str(cursor):
                raise JacadConnectionError("Cursor JACAD repetido; sincronização interrompida para evitar loop.")
            seen_cursors.add(marker)
            cursor = next_cursor
        raise JacadConnectionError("Limite de páginas JACAD atingido; sync parcial não foi ingerido.")
