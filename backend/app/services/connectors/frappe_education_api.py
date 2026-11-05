"""Allowlisted, read-only Frappe Education/ERPNext REST client.

The MIRA API never calls arbitrary Frappe RPC methods or returns raw financial
or academic documents. External requests use HTTPS, a previously approved
tenant host, bounded pagination, no redirects and no environment proxy.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from app.services.connectors.destination_policy import normalize_hostname
from app.services.connectors.tenant_destinations import (
    authorize_connector_client, require_destination_authorization,
)


class FrappeApiError(RuntimeError):
    def __init__(self, code: str, message: str = "Consulta ao Frappe indisponível."):
        super().__init__(message)
        self.code = code


# Financial records are only source-system snapshots; never treat them as proof
# of payment, settlement, a current balance or an authorization to collect.
_ALLOWED_FIELDS: dict[str, tuple[str, ...]] = {
    "Student": ("name", "student_name", "student_email_id", "program", "enabled"),
    "Student Attendance": ("name", "student", "date", "status", "student_group"),
    "Assessment Result": ("name", "student", "assessment_plan", "total_score", "grade"),
    "Sales Invoice": (
        "name", "student", "posting_date", "due_date", "grand_total",
        "outstanding_amount", "status", "currency", "docstatus",
    ),
}


def _public_record(doctype: str, record: dict[str, Any]) -> dict[str, Any]:
    return {key: record.get(key) for key in _ALLOWED_FIELDS[doctype] if key in record}


class FrappeEducationClient:
    def __init__(
        self, *, hostname: str, api_key: str, api_secret: str,
        authorization_token: object | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        require_destination_authorization(authorization_token)
        self.hostname = normalize_hostname(hostname)
        if not api_key or not api_secret:
            raise ValueError("Credenciais Frappe incompletas.")
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url="https://" + self.hostname,
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        )
        self._headers = {
            "Authorization": "token " + api_key + ":" + api_secret,
            "Accept": "application/json",
        }

    @classmethod
    async def for_tenant(
        cls, db, *, tenant_id: str, hostname: str, api_key: str, api_secret: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> "FrappeEducationClient":
        authorization = await authorize_connector_client(
            db, tenant_id=tenant_id, connector_key="frappe_ies",
            url="https://" + normalize_hostname(hostname),
        )
        return cls(
            hostname=hostname, api_key=api_key, api_secret=api_secret,
            authorization_token=authorization, http_client=http_client,
        )

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "FrappeEducationClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _read(self, path: str, params: Mapping[str, str | int] | None = None) -> dict[str, Any]:
        # Only callers in this class supply the fixed route templates.
        try:
            response = await self._http.get(path, params=params, headers=self._headers)
        except httpx.RequestError as exc:
            raise FrappeApiError("transport_error") from exc
        if response.status_code in (301, 302, 303, 307, 308):
            raise FrappeApiError("unexpected_redirect")
        if response.status_code == 404:
            raise FrappeApiError("not_found")
        if response.status_code in (401, 403):
            raise FrappeApiError("remote_access_denied")
        if response.status_code == 429 or response.status_code >= 500:
            raise FrappeApiError("upstream_unavailable")
        if response.status_code >= 400:
            raise FrappeApiError("upstream_validation_error")
        if len(response.content) > 1024 * 1024:
            raise FrappeApiError("response_too_large")
        try:
            result = response.json()
        except ValueError as exc:
            raise FrappeApiError("invalid_json") from exc
        if not isinstance(result, dict):
            raise FrappeApiError("invalid_payload")
        return result

    async def test_connection(self) -> bool:
        result = await self._read("/api/method/frappe.auth.get_logged_user")
        return isinstance(result.get("message"), str) and bool(result["message"])

    async def get_student(self, frappe_student_name: str) -> dict[str, Any]:
        if not frappe_student_name or len(frappe_student_name) > 180:
            raise ValueError("Identificador do aluno Frappe inválido.")
        result = await self._read("/api/resource/Student/" + quote(frappe_student_name, safe=""))
        data = result.get("data")
        if not isinstance(data, dict) or data.get("name") != frappe_student_name:
            raise FrappeApiError("invalid_student_response")
        return _public_record("Student", data)

    async def list_for_student(
        self, doctype: str, frappe_student_name: str, *,
        offset: int = 0, limit: int = 30,
    ) -> dict[str, Any]:
        if doctype not in ("Student Attendance", "Assessment Result", "Sales Invoice"):
            raise ValueError("Tipo de documento não autorizado.")
        if not frappe_student_name or len(frappe_student_name) > 180:
            raise ValueError("Identificador do aluno Frappe inválido.")
        if offset < 0 or offset > 10000 or limit < 1 or limit > 100:
            raise ValueError("Paginação não permitida.")
        fields = _ALLOWED_FIELDS[doctype]
        response = await self._read(
            "/api/resource/" + quote(doctype, safe=""),
            {
                "fields": json.dumps(fields),
                "filters": json.dumps([["student", "=", frappe_student_name]]),
                "limit_start": offset,
                "limit_page_length": limit,
            },
        )
        records = response.get("data")
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            raise FrappeApiError("invalid_collection_response")
        # Defensive filtering: upstream service-account scope must not be
        # trusted as a substitute for MIRA's student identity authorization.
        if any(row.get("student") != frappe_student_name for row in records):
            raise FrappeApiError("student_scope_mismatch")
        return {
            "items": [_public_record(doctype, row) for row in records],
            "offset": offset, "limit": limit, "has_more": len(records) == limit,
            "source": "frappe",
            "snapshot_only": doctype == "Sales Invoice",
        }
