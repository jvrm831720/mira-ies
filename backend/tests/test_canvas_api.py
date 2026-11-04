from urllib.parse import parse_qs

import httpx
import pytest

from app.services.connectors.canvas_api import (
    CanvasApiClient,
    CanvasAuthenticationError,
    CanvasConfig,
    CanvasContractError,
)


def test_config_requires_https_and_valid_token():
    config = CanvasConfig("https://school.example.edu/canvas", "token")
    assert config.api_base_url() == "https://school.example.edu/canvas/api/v1/"
    with pytest.raises(ValueError, match="HTTPS"):
        CanvasConfig("http://school.example.edu", "token").api_base_url()
    with pytest.raises(ValueError, match="HTTPS"):
        CanvasConfig("https://user:pass@school.example.edu", "token").api_base_url()
    with pytest.raises(ValueError, match="obrigatório"):
        CanvasConfig("https://school.example.edu", "").api_base_url()


@pytest.mark.asyncio
async def test_get_uses_bearer_token_and_get_method():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert request.url.path == "/canvas/api/v1/courses"
        return httpx.Response(200, json=[{"id": 12, "name": "Course"}])

    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu/canvas", "secret-token"),
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.list_courses()
    assert result[0]["id"] == 12


@pytest.mark.asyncio
async def test_course_users_and_assignment_submissions_paths():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=[])

    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu", "token"),
        transport=httpx.MockTransport(handler),
    ) as client:
        await client.list_course_users(5)
        await client.list_assignment_submissions(5, 8)
        await client.list_missing_submissions(13)
    assert seen == [
        "/api/v1/courses/5/users",
        "/api/v1/courses/5/assignments/8/submissions",
        "/api/v1/users/13/missing_submissions",
    ]


@pytest.mark.asyncio
async def test_rejects_non_get_resources_and_invalid_ids():
    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu", "token"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
    ) as client:
        with pytest.raises(ValueError, match="não permitido"):
            await client.get("courses/1/enrollments/2")
        with pytest.raises(ValueError, match="inteiro positivo"):
            await client.list_course_users(True)


@pytest.mark.asyncio
async def test_handles_authentication_errors_without_leaking_response():
    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu", "token"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"errors": [{"message": "private detail"}]})
        ),
    ) as client:
        with pytest.raises(CanvasAuthenticationError) as exc:
            await client.list_courses()
    assert "private detail" not in str(exc.value)


@pytest.mark.asyncio
async def test_bounded_pagination_follows_same_origin_next_link():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json=[{"id": 1}],
                headers={"Link": '</api/v1/courses?page=2>; rel="next", </api/v1/courses?page=1>; rel="first"'},
            )
        return httpx.Response(200, json=[{"id": 2}])

    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu", "token"),
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.get_all("courses", max_pages=2)
    assert result == [{"id": 1}, {"id": 2}]
    assert calls == ["/api/v1/courses", "/api/v1/courses"]


@pytest.mark.asyncio
async def test_pagination_rejects_external_links():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"id": 1}],
            headers={"Link": '<https://attacker.example/steal>; rel="next"'},
        )

    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu", "token"),
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(CanvasContractError, match="fora da origem"):
            await client.get_all("courses")


@pytest.mark.asyncio
async def test_rejects_invalid_pagination_limit_and_non_list_payload():
    async with CanvasApiClient(
        CanvasConfig("https://school.example.edu", "token"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"unexpected": True})),
    ) as client:
        with pytest.raises(ValueError, match="max_pages"):
            await client.get_all("courses", max_pages=0)
        with pytest.raises(CanvasContractError, match="lista JSON"):
            await client.get_all("courses")
