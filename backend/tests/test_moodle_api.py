from urllib.parse import parse_qs

import httpx
import pytest

from app.services.connectors.moodle_api import (
    MoodleApiClient,
    MoodleAuthenticationError,
    MoodleConfig,
    MoodleFunctionUnavailableError,
)


def test_config_builds_endpoint_and_rejects_insecure_urls():
    config = MoodleConfig("https://campus.example.edu/moodle/", "test-token")
    assert config.endpoint_url() == "https://campus.example.edu/moodle/webservice/rest/server.php"
    with pytest.raises(ValueError, match="HTTPS"):
        MoodleConfig("http://campus.example.edu", "test-token").endpoint_url()
    with pytest.raises(ValueError, match="HTTPS"):
        MoodleConfig("https://user:pass@campus.example.edu", "test-token").endpoint_url()


@pytest.mark.asyncio
async def test_site_info_posts_token_in_body_and_parses_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == "https://campus.example.edu/moodle/webservice/rest/server.php"
        form = parse_qs(request.content.decode())
        assert form["wstoken"] == ["secret-token"]
        assert form["wsfunction"] == ["core_webservice_get_site_info"]
        assert form["moodlewsrestformat"] == ["json"]
        assert "secret-token" not in str(request.url)
        return httpx.Response(200, json={"sitename": "Campus Test", "userid": 7})

    async with MoodleApiClient(
        MoodleConfig("https://campus.example.edu/moodle", "secret-token"),
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.get_site_info()
    assert result["sitename"] == "Campus Test"


@pytest.mark.asyncio
async def test_nested_array_params_follow_moodle_rest_form_convention():
    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        assert form["field"] == ["idnumber"]
        assert form["values[0]"] == ["STU-1"]
        assert form["values[1]"] == ["STU-2"]
        return httpx.Response(200, json=[{"id": 10, "idnumber": "STU-1"}])

    async with MoodleApiClient(
        MoodleConfig("https://campus.example.edu", "token"),
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.get_users_by_field("idnumber", ["STU-1", "STU-2"])
    assert result[0]["id"] == 10


@pytest.mark.asyncio
async def test_rejects_write_functions_and_reserved_auth_params():
    async with MoodleApiClient(
        MoodleConfig("https://campus.example.edu", "token"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    ) as client:
        with pytest.raises(ValueError, match="read-only"):
            await client.call("core_user_create_users", {"users": []})
        with pytest.raises(ValueError, match="gerenciados"):
            await client.call("core_webservice_get_site_info", {"wstoken": "override"})


@pytest.mark.asyncio
async def test_invalid_token_error_is_sanitized():
    async with MoodleApiClient(
        MoodleConfig("https://campus.example.edu", "token"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "exception": "moodle_exception",
                "errorcode": "invalidtoken",
                "message": "sensitive backend detail",
            })
        ),
    ) as client:
        with pytest.raises(MoodleAuthenticationError) as exc:
            await client.get_site_info()
    assert "sensitive backend detail" not in str(exc.value)


@pytest.mark.asyncio
async def test_function_not_enabled_is_explicit():
    async with MoodleApiClient(
        MoodleConfig("https://campus.example.edu", "token"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "exception": "webservice_access_exception",
                "errorcode": "functionnotavailable",
                "message": "function unavailable",
            })
        ),
    ) as client:
        with pytest.raises(MoodleFunctionUnavailableError, match="core_webservice_get_site_info"):
            await client.get_site_info()


@pytest.mark.asyncio
async def test_user_lookup_rejects_empty_values_and_invalid_field():
    async with MoodleApiClient(
        MoodleConfig("https://campus.example.edu", "token"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
    ) as client:
        with pytest.raises(ValueError, match="Campo"):
            await client.get_users_by_field("password", ["x"])
        with pytest.raises(ValueError, match="identificador"):
            await client.get_users_by_field("idnumber", [])
        with pytest.raises(ValueError, match="inteiro positivo"):
            await client.get_user_courses(True)
