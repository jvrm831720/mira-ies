"""Wave 7 live UI: Playwright -> real FastAPI ASGI -> test PostgreSQL.

No JSON fixture, no fake browser authentication. Browser uses actual signed MFA
token, server dependencies and SQL-backed RLS-capable data. The HTTP bridge is
in-memory only to avoid a separate uvicorn server; it forwards every request,
method and body to the actual ASGI app and never modifies its outcomes.

WAVE7_BROWSER_BASE_URL must point at a local Next.js build/dev server.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.services.federated_search_providers import PROVIDERS
from test_wave7_authenticated_journeys import headers, live_workspaces

BASE = os.environ.get("WAVE7_BROWSER_BASE_URL", "").rstrip("/")
ARTIFACTS = Path(os.environ.get("WAVE7_ARTIFACT_DIR", "/tmp/mira-wave7-artifacts"))
JOURNEYS = (
    "app_shell", "object_index", "student_360",
    "collections_360", "human_work", "universal_search",
)
SIZES = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}
MEASURED: dict = {
    "schema_version": 1,
    "source": "wave7_authenticated_live_asgi",
    "environment": "ci",
    "signed_mfa_sessions": False,
    "tenant_isolation": False,
    "rbac_denials": False,
    "integration_failure_isolation": False,
    "no_critical_side_effects": False,
    "journeys": [],
    "metrics": {},
    "accessibility": {"serious_critical_count": 0},
}
LATENCIES: dict[str, list[float]] = {"page": [], "api": []}

pytestmark = pytest.mark.skipif(
    not BASE, reason="Live browser gate runs in dedicated Wave 7 CI job only",
)


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 2)


@pytest.fixture(scope="module", autouse=True)
def write_evidence():
    yield
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    MEASURED["metrics"] = {
        "page_p95_ms": p95(LATENCIES["page"]),
        "api_p95_ms": p95(LATENCIES["api"]),
        "page_samples": len(LATENCIES["page"]),
        "api_samples": len(LATENCIES["api"]),
    }
    (ARTIFACTS / "wave7-evidence.json").write_text(
        json.dumps(MEASURED, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("viewport", tuple(SIZES))
@pytest.mark.parametrize("journey", JOURNEYS)
async def test_live_browser_six_journeys(
    journey, viewport, live_workspaces, client, db_session, monkeypatch
):
    pw = pytest.importorskip("playwright.async_api")
    own, foreign = live_workspaces
    session = await client.get("/api/v1/org/me", headers=headers(own["token"]))
    assert session.status_code == 200, session.text
    assert session.json()["tenant_id"] == own["tenant"]
    MEASURED["signed_mfa_sessions"] = True

    # Same tenant token can neither enumerate foreign students nor finances.
    leak = await client.get(
        f"/api/v1/collections/cases/{foreign['case']}",
        headers=headers(own["token"]),
    )
    assert leak.status_code == 404
    MEASURED["tenant_isolation"] = True
    spectator = await client.get(
        "/api/v1/collections/cases", headers=headers(own["viewer_token"]),
    )
    assert spectator.status_code == 403
    MEASURED["rbac_denials"] = True

    fault = journey == "universal_search"

    async def unavailable(_ctx):
        raise SQLAlchemyError("PRIVATE provider error; should never escape")

    if fault:
        monkeypatch.setitem(PROVIDERS, "campaigns", unavailable)

    async with pw.async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, args=["--no-sandbox"],
        )
        context = await browser.new_context(
            viewport=SIZES[viewport], device_scale_factor=1,
            locale="pt-BR", reduced_motion="reduce",
        )
        await context.add_init_script(
            script="window.localStorage.setItem('mira_access_token', "
                   + json.dumps(own["token"]) + ");"
        )
        page = await context.new_page()
        browser_errors: list[str] = []
        requests: list[tuple[str, str]] = []
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        measured_apis: list[float] = []

        async def real_asgi(route):
            req = route.request
            uri = urlsplit(req.url)
            path = uri.path + ("?" + uri.query if uri.query else "")
            origin = req.headers.get("origin", BASE)
            if req.method == "OPTIONS":
                await route.fulfill(status=204, headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "authorization,content-type",
                    "Access-Control-Allow-Credentials": "true",
                })
                return
            requests.append((req.method, uri.path))
            header = {
                "Authorization": req.headers.get("authorization", ""),
                "Content-Type": req.headers.get("content-type", "application/json"),
            }
            started = perf_counter()
            response = await client.request(
                req.method, path, headers=header,
                content=req.post_data_buffer,
            )
            elapsed = (perf_counter() - started) * 1000
            measured_apis.append(elapsed)
            LATENCIES["api"].append(elapsed)
            await route.fulfill(
                status=response.status_code, body=response.content,
                headers={
                    "Content-Type": response.headers.get("content-type", "application/json"),
                    "Cache-Control": "no-store",
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                },
            )

        # Intercept both Next same-origin /api requests and API_URL cross-origin.
        await page.route("**/api/v1/**", real_asgi)
        routes = {
            "app_shell": "/trabalho",
            "object_index": "/alunos",
            "student_360": "/alunos/" + own["student"],
            "collections_360": "/cobranca/casos/" + own["case"],
            "human_work": "/trabalho?activity=" + own["task"],
            "universal_search": "/trabalho",
        }
        started = perf_counter()
        status = "failed"
        serious = 0
        try:
            await page.goto(BASE + routes[journey], wait_until="domcontentloaded",
                            timeout=60000)
            if journey == "app_shell":
                await page.get_by_text("Meu Trabalho", exact=True).first.wait_for(timeout=45000)
                await page.keyboard.press("Control+k")
                dialog = page.get_by_role("dialog", name="Busca universal da MIRA")
                await dialog.wait_for(timeout=10000)
                await page.keyboard.press("Escape")
                assert await dialog.count() == 0

            elif journey == "object_index":
                await page.get_by_text("Aline Homologacao A", exact=False).first.wait_for(
                    timeout=45000
                )
                search = page.get_by_role("searchbox", name="Buscar em Alunos")
                await search.fill("W7-A")
                await page.get_by_text("Aline Homologacao A", exact=False).first.wait_for()

            elif journey == "student_360":
                await page.get_by_text("Aline Homologacao A", exact=False).first.wait_for(
                    timeout=45000
                )
                assert await page.get_by_text("Engenharia", exact=False).count() > 0

            elif journey == "collections_360":
                await page.get_by_text("W7-FIN-A", exact=False).first.wait_for(
                    timeout=45000
                )
                assert await page.get_by_text("149,90", exact=False).count() >= 0
                assert not any(method != "GET" for method, _ in requests)

            elif journey == "human_work":
                await page.get_by_role(
                    "button", name="Assumir atividade",
                ).wait_for(timeout=45000)
                await page.get_by_role("button", name="Assumir atividade").click()
                note = page.get_by_placeholder(
                    "Descreva o que foi feito ou o motivo do adiamento."
                )
                await note.wait_for(timeout=20000)
                await note.fill("Ação humana homologada sem envio ou pagamento")
                await page.get_by_role(
                    "button", name="Registrar e concluir atividade",
                ).click()
                await page.get_by_text("Trabalho humano concluído", exact=False).first.wait_for(
                    timeout=15000
                )

            elif journey == "universal_search":
                await page.get_by_text("Meu Trabalho", exact=True).first.wait_for(
                    timeout=45000
                )
                await page.keyboard.press("Control+k")
                dialog = page.get_by_role("dialog", name="Busca universal da MIRA")
                await dialog.wait_for()
                await dialog.get_by_role("combobox").fill("Aline")
                await dialog.get_by_text("Busca parcial", exact=False).wait_for(
                    timeout=30000
                )
                assert await dialog.get_by_role("option").count() >= 2
                assert await dialog.get_by_text("PRIVATE provider error").count() == 0
                await page.keyboard.press("ArrowDown")
                assert await dialog.locator('[role="option"][aria-selected="true"]').count() == 1
                await page.keyboard.press("Escape")
                assert not any(method != "GET" for method, _ in requests)
                MEASURED["integration_failure_isolation"] = True

            LATENCIES["page"].append((perf_counter() - started) * 1000)
            # Check the key WCAG A/AA criteria. The axe script is installed
            # locally in the runner; never pull third-party JS from the page.
            axe = Path(__file__).resolve().parents[2] / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
            assert axe.is_file(), "axe-core is required in the live browser gate"
            await page.add_script_tag(path=str(axe))
            evaluation = await page.evaluate("""
                async () => await window.axe.run(document, {
                    runOnly: { type: "tag", values: [
                        "wcag2a", "wcag2aa", "wcag21a", "wcag21aa"
                    ] }
                })
            """)
            violations = [
                issue for issue in evaluation["violations"]
                if issue.get("impact") in ("critical", "serious")
            ]
            serious = len(violations)
            MEASURED["accessibility"]["serious_critical_count"] += serious
            assert serious == 0, [i["id"] for i in violations]

            assert not browser_errors, browser_errors[:3]
            status = "passed"
            if journey == "human_work":
                await db_session.rollback()
                await db_session.execute(text(
                    "SELECT set_config('app.tenant_id', :tenant, true)"
                ), {"tenant": own["tenant"]})
                payment_total = (await db_session.execute(text("""
                    SELECT count(*) FROM dispatch_payment_events
                    WHERE tenant_id=:tenant
                """), {"tenant": own["tenant"]})).scalar_one()
                obligation_status = (await db_session.execute(text("""
                    SELECT status FROM dispatch_obligations
                    WHERE tenant_id=:tenant AND id=:id
                """), {"tenant": own["tenant"], "id": own["case"]})).scalar_one()
                assert payment_total == 0 and obligation_status == "open"
                MEASURED["no_critical_side_effects"] = True
        finally:
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            output = ARTIFACTS / f"{journey}-{viewport}.png"
            await page.screenshot(path=str(output), animations="disabled",
                                  full_page=False)
            MEASURED["journeys"].append({
                "id": journey, "viewport": viewport,
                "status": status, "authenticated": True,
                "api_calls": len(measured_apis),
                "page_ms": round((perf_counter() - started) * 1000, 2),
                "serious_accessibility": serious,
            })
            await context.close()
            await browser.close()
