"""Frappe bridge contract tests: no writes and no cross-student disclosure."""
import json

import httpx
import pytest

from app.services.connectors.frappe_education_api import (
    FrappeApiError, FrappeEducationClient,
)
from app.services.connectors.destination_policy import normalize_hostname


async def test_frappe_client_uses_token_auth_and_fixed_get_routes():
    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.path.endswith("/frappe.auth.get_logged_user"):
            return httpx.Response(200, json={"message": "readonly@institution.edu"})
        return httpx.Response(200, json={"data": {"name": "EDU-001", "student_name": "Aluno teste"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://ies.example.edu", transport=transport) as http:
        client = FrappeEducationClient(
            hostname="ies.example.edu", api_key="key12345", api_secret="secret12345",
            http_client=http,
        )
        assert await client.test_connection() is True
        record = await client.get_student("EDU-001")
        assert record == {"name": "EDU-001", "student_name": "Aluno teste"}

    assert all(request.method == "GET" for request in observed)
    assert all(request.url.host == "ies.example.edu" for request in observed)
    assert all(request.headers["Authorization"] == "token key12345:secret12345" for request in observed)


async def test_frappe_client_rejects_remote_records_of_other_students():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.url.params["filters"]) == [["student", "=", "EDU-001"]]
        return httpx.Response(200, json={"data": [
            {"name": "INV-2", "student": "EDU-OTHER", "outstanding_amount": 50}
        ]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://ies.example.edu", transport=transport) as http:
        client = FrappeEducationClient(
            hostname="ies.example.edu", api_key="key12345", api_secret="secret12345",
            http_client=http,
        )
        with pytest.raises(FrappeApiError) as error:
            await client.list_for_student("Sales Invoice", "EDU-001")
    assert error.value.code == "student_scope_mismatch"


async def test_frappe_client_restricts_resource_and_pagination():
    async with httpx.AsyncClient(base_url="https://ies.example.edu") as http:
        client = FrappeEducationClient(
            hostname="ies.example.edu", api_key="key12345", api_secret="secret12345",
            http_client=http,
        )
        with pytest.raises(ValueError):
            await client.list_for_student("Payment Entry", "EDU-001")
        with pytest.raises(ValueError):
            await client.list_for_student("Sales Invoice", "EDU-001", limit=1000)


@pytest.mark.parametrize("host", [
    "127.0.0.1", "localhost", "169.254.169.254",
    "localhost.localdomain", "metadata.google.internal", "http://ies.example.edu",
])
def test_frappe_host_rejects_private_or_url_values(host):
    with pytest.raises(ValueError):
        normalize_hostname(host)


async def test_frappe_connection_endpoint_requires_auth(client):
    response = await client.get("/api/v1/integrations/frappe-ies/connection")
    assert response.status_code == 401


async def test_frappe_configuration_requires_settings_permission(client, auth_headers):
    response = await client.get(
        "/api/v1/integrations/frappe-ies/connection", headers=auth_headers,
    )
    assert response.status_code == 403
