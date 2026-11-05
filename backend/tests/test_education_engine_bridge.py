"""Contracts for the owned, multi-site Frappe bridge.

Run against the disposable local PostgreSQL database, not production. All
upstream HTTP in these tests is mocked; never sends messages or takes payment.
"""
import json

import httpx
import pytest
from fastapi import HTTPException

from app.api.education_engine import _link
from app.core.auth import AuthContext
from app.models.education_engine import TenantEducationEngineStudent
from app.models.student import Student, UploadBatch
from app.services.education_engine_client import (
    EducationEngineClient, EducationEngineError, checked_engine_url, checked_site,
)
from app.services.education_engine_secrets import encrypt_credential, decrypt_credential


def _client(transport):
    return EducationEngineClient(
        base_url="https://engine.example.com",
        site="ies-1.example.com",
        api_key="readonlykey",
        api_secret="readonlysecret",
        app_env="testing",
        transport=transport,
    )


async def test_profile_is_allowlisted_and_frappe_token_is_server_only():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("get_logged_user"):
            return httpx.Response(200, json={"message": "readonly@ies.example"})
        return httpx.Response(200, json={
            "data": {
                "name": "EDU-STU-001", "student_name": "Ana",
                "date_of_birth": "2000-01-01", "blood_group": "A+",
            },
        })

    engine = _client(httpx.MockTransport(handler))
    try:
        assert await engine.verify_service_account() is True
        profile = await engine.student("EDU-STU-001")
    finally:
        await engine.aclose()
    assert profile == {"name": "EDU-STU-001", "student_name": "Ana"}
    assert all(req.method == "GET" for req in requests)
    assert all(req.url.host == "engine.example.com" for req in requests)
    assert all(req.headers["Host"] == "ies-1.example.com" for req in requests)
    assert all(req.headers["X-Frappe-Site-Name"] == "ies-1.example.com" for req in requests)
    assert all(req.headers["Authorization"] == "token readonlykey:readonlysecret" for req in requests)


async def test_fees_and_attendance_filter_by_verified_student():
    def handler(request: httpx.Request):
        assert json.loads(request.url.params["filters"]) == [["student", "=", "EDU-STU-001"]]
        assert request.url.path.endswith("/api/resource/Fees")
        assert "limit_start" in request.url.params
        return httpx.Response(200, json={
            "data": [{
                "name": "EDU-FEE-001", "student": "EDU-STU-001",
                "outstanding_amount": 55, "hidden_internal": "do not expose",
            }],
        })
    engine = _client(httpx.MockTransport(handler))
    try:
        data = await engine.records("fees", "EDU-STU-001", limit=20)
    finally:
        await engine.aclose()
    assert data["financial_snapshot_only"] is True
    assert data["items"] == [{
        "name": "EDU-FEE-001", "student": "EDU-STU-001", "outstanding_amount": 55,
    }]


async def test_unauthorized_remote_student_is_rejected():
    engine = _client(httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "data": [{"name": "EDU-FEE-999", "student": "OTHER-IES"}],
        }),
    ))
    try:
        with pytest.raises(EducationEngineError) as error:
            await engine.records("fees", "EDU-STU-001")
    finally:
        await engine.aclose()
    assert error.value.code == "cross_student_response"


async def test_redirects_and_unlisted_doctypes_fail_closed():
    engine = _client(httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "http://localhost/secrets"}),
    ))
    try:
        with pytest.raises(EducationEngineError) as error:
            await engine.student("EDU-STU-001")
        with pytest.raises(ValueError):
            await engine.records("payment-entries", "EDU-STU-001")
    finally:
        await engine.aclose()
    assert error.value.code == "redirect_denied"

@pytest.mark.parametrize("bad_id", ["..", "../admin", "bad\\\\path", "name?filter=x", "bad#fragment", "percent%2Fslash"])
async def test_frappe_student_id_is_not_an_arbitrary_url_segment(bad_id):
    engine = _client(httpx.MockTransport(
        lambda request: pytest.fail("unsafe student name reached the network"),
    ))
    try:
        with pytest.raises(ValueError):
            await engine.student(bad_id)
    finally:
        await engine.aclose()


@pytest.mark.parametrize("value, env", [
    ("http://169.254.169.254", "production"),
    ("http://127.0.0.1:8080", "production"),
    ("http://example.com", "production"),
    ("https://user:pass@example.com", "production"),
    ("https://engine.example.com/api/method", "production"),
])
def test_engine_endpoint_guard_rejects_unsafe_origin(value, env):
    with pytest.raises(ValueError):
        checked_engine_url(value, env)


def test_site_must_be_exactly_approved_and_one_origin_per_tenant():
    assert checked_site("ies-1.example.com", "ies-1.example.com,ies-2.example.com") == "ies-1.example.com"
    with pytest.raises(ValueError):
        checked_site("ies-2.example.com", "ies-1.example.com")
    with pytest.raises(ValueError):
        checked_site("ies-1.example.com.evil.net", "ies-1.example.com")
    assert checked_engine_url("http://frappe.internal:8080", "production") == "http://frappe.internal:8080"


def test_token_encrypted_at_rest():
    ciphertext = encrypt_credential("readonlysecret")
    assert "readonlysecret" not in ciphertext
    assert decrypt_credential(ciphertext) == "readonlysecret"


async def test_engine_api_requires_session(client, auth_headers):
    unauth = await client.get("/api/v1/education-engine/connection")
    assert unauth.status_code == 401
    # Legacy service API keys are not administrators and cannot configure Frappe.
    forbidden = await client.get(
        "/api/v1/education-engine/connection", headers=auth_headers,
    )
    assert forbidden.status_code == 403


async def test_student_identity_cannot_cross_institution(
    tenant_factory, db_session,
):
    institution_a, _ = await tenant_factory(slug="ies-a", name="IES A")
    institution_b, _ = await tenant_factory(slug="ies-b", name="IES B")
    batch = UploadBatch(
        tenant_id=institution_b.id, filename="seed.csv", original_filename="seed.csv",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=institution_b.id, batch_id=batch.id, matricula="B-001",
        nome="Aluno de outra IES",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(TenantEducationEngineStudent(
        tenant_id=institution_b.id, student_id=student.id,
        frappe_student_id="B-REMOTE-001",
    ))
    await db_session.commit()
    auth = AuthContext(
        tenant=institution_a, tenant_id=institution_a.id, tenant_slug=institution_a.slug,
    )
    with pytest.raises(HTTPException) as error:
        await _link(db_session, auth, student.id)
    assert error.value.status_code == 404
