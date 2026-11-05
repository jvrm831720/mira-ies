"""Read-only bridge from the Render MIRA API to the MIRA-operated Frappe bench.

No generic /api/method proxy, arbitrary URL, PDF fetch, write verb or shared
Administrator token. Only allowlisted DocTypes and fields are exposed.
"""
from __future__ import annotations

import ipaddress
import json
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx


class EducationEngineError(RuntimeError):
    def __init__(self, code: str):
        super().__init__("Falha na consulta ao motor acadêmico.")
        self.code = code


# Derived from frappe/education@1f89e2e (version-15.1) DocType JSON definitions.
ALLOWED_COLLECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "attendance": (
        "Student Attendance",
        ("name", "student", "date", "status", "student_group", "course_schedule"),
    ),
    "grades": (
        "Assessment Result",
        ("name", "student", "course", "academic_year", "academic_term",
         "assessment_plan", "total_score", "maximum_score", "grade"),
    ),
    "fees": (
        "Fees",
        ("name", "student", "posting_date", "due_date", "grand_total",
         "outstanding_amount", "currency", "docstatus", "program", "academic_term"),
    ),
    "enrollments": (
        "Program Enrollment",
        ("name", "student", "program", "academic_year", "academic_term",
         "enrollment_date", "student_batch_name", "docstatus"),
    ),
}
PROFILE_FIELDS = frozenset((
    "name", "student_name", "first_name", "middle_name", "last_name",
    "student_email_id", "student_mobile_number", "enabled", "joining_date",
))


def checked_site(name: str, allowed_sites: str) -> str:
    if not isinstance(name, str) or not 1 <= len(name) <= 200:
        raise ValueError("Site acadêmico inválido.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", name):
        raise ValueError("Site acadêmico inválido.")
    if any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-") for part in name.split(".")):
        raise ValueError("Site acadêmico inválido.")
    allowlist = {item.strip().lower() for item in allowed_sites.split(",") if item.strip()}
    if name not in allowlist:
        raise ValueError("Site não autorizado pelo ambiente da MIRA.")
    return name


def checked_engine_url(value: str, app_env: str) -> str:
    """Config only from Render backend env, never from an HTTP request or tenant data."""
    if not value:
        raise ValueError("MIRA_EDUCATION_ENGINE_URL não configurada.")
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("URL do motor acadêmico inválida.")
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Use apenas a origem fixa do motor acadêmico.")
    host = parsed.hostname.lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if host in {"localhost", "127.0.0.1", "::1"} or (ip and ip.is_loopback):
        if app_env not in ("development", "testing"):
            raise ValueError("Motor local não permitido fora do desenvolvimento.")
    elif ip is not None:
        raise ValueError("IP literal proibido como origem remota.")
    if parsed.scheme == "http" and not (
        (app_env in ("development", "testing") and (host == "localhost" or (ip and ip.is_loopback)))
        or host.endswith(".internal")
    ):
        raise ValueError("Use HTTPS ou uma origem Render privada .internal.")
    return value.rstrip("/")


class EducationEngineClient:
    def __init__(
        self, *, base_url: str, site: str, api_key: str, api_secret: str,
        app_env: str = "production", transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        checked_engine_url(base_url, app_env)
        if not api_key or not api_secret:
            raise ValueError("Credencial incompleta.")
        self.site = site
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
            trust_env=False,
            follow_redirects=False,
            transport=transport,
            headers={
                "Authorization": f"token {api_key}:{api_secret}",
                "Host": site,
                "X-Frappe-Site-Name": site,
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "EducationEngineClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with self._client.stream("GET", path, params=params) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    raise EducationEngineError("redirect_denied")
                if response.status_code == 404:
                    raise EducationEngineError("remote_not_found")
                if response.status_code in (401, 403):
                    raise EducationEngineError("remote_permission_denied")
                if response.status_code == 429 or response.status_code >= 500:
                    raise EducationEngineError("upstream_unavailable")
                if response.status_code >= 400:
                    raise EducationEngineError("upstream_rejected")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 1024 * 1024:
                        raise EducationEngineError("response_too_large")
        except httpx.RequestError as exc:
            raise EducationEngineError("transport_failure") from exc
        try:
            result = json.loads(content)
        except (ValueError, UnicodeDecodeError) as exc:
            raise EducationEngineError("invalid_json") from exc
        if not isinstance(result, dict):
            raise EducationEngineError("invalid_payload")
        return result

    async def verify_service_account(self) -> bool:
        payload = await self._get("/api/method/frappe.auth.get_logged_user")
        return isinstance(payload.get("message"), str) and bool(payload["message"])

    async def student(self, remote_id: str) -> dict[str, Any]:
        if not remote_id or len(remote_id) > 180 or any(ord(x) < 32 or ord(x) == 127 for x in remote_id):
            raise ValueError("Identificador acadêmico inválido.")
        response = await self._get("/api/resource/Student/" + quote(remote_id, safe=""))
        data = response.get("data")
        if not isinstance(data, dict) or data.get("name") != remote_id:
            raise EducationEngineError("student_mismatch")
        return {k: data[k] for k in PROFILE_FIELDS if k in data}

    async def records(
        self, kind: str, remote_student_id: str, *, offset: int = 0, limit: int = 30,
    ) -> dict[str, Any]:
        if kind not in ALLOWED_COLLECTIONS:
            raise ValueError("Recurso acadêmico não permitido.")
        if not remote_student_id or len(remote_student_id) > 180:
            raise ValueError("Aluno remoto inválido.")
        if not 0 <= offset <= 10000 or not 1 <= limit <= 100:
            raise ValueError("Paginação inválida.")
        doctype, fields = ALLOWED_COLLECTIONS[kind]
        result = await self._get(
            "/api/resource/" + quote(doctype, safe=""),
            {
                "fields": json.dumps(fields),
                "filters": json.dumps([["student", "=", remote_student_id]]),
                "limit_start": offset,
                "limit_page_length": limit,
            },
        )
        rows = result.get("data")
        if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
            raise EducationEngineError("invalid_collection")
        if any(row.get("student") != remote_student_id for row in rows):
            raise EducationEngineError("cross_student_response")
        return {
            "items": [{k: row[k] for k in fields if k in row} for row in rows],
            "offset": offset, "limit": limit, "has_more": len(rows) == limit,
            "source": "mira_education_engine",
            "financial_snapshot_only": kind == "fees",
        }
