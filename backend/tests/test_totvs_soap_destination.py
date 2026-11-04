import httpx
import pytest

from app.services.connectors.soap import TotvsReadOnlySoapClient
from app.services.connectors.transport import ERPRequestContext


@pytest.mark.asyncio
async def test_soap_for_tenant_uses_persisted_destination(monkeypatch):
    async def authorize(db, *, tenant_id, connector_key, url):
        assert tenant_id == "tenant-a"
        assert connector_key == "totvs_rm_soap"
        assert url == "https://untrusted-config.example/ws"
        return "https://approved.example/ws"

    monkeypatch.setattr(
        "app.services.connectors.soap.authorize_tenant_destination", authorize
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "approved.example"
        assert request.method == "POST"
        return httpx.Response(
            200,
            content=(
                b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                b'xmlns:t="http://www.totvs.com/"><s:Body><t:ReadRecordResponse>'
                b'<t:ReadRecordResult>&lt;ROOT/&gt;</t:ReadRecordResult>'
                b'</t:ReadRecordResponse></s:Body></s:Envelope>'
            ),
        )

    client = await TotvsReadOnlySoapClient.for_tenant(
        object(),
        tenant_id="tenant-a",
        endpoint="https://untrusted-config.example/ws",
        username="user",
        password="secret",
        context=ERPRequestContext(codcoligada="1"),
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await client.read_record(dataserver="EduAlunoData", primary_key="1") == "<ROOT/>"
    finally:
        await client.aclose()
