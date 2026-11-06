"""Browser visual regression of real Next.js pages against isolated synthetic API fixtures.

The script NEVER connects to production and blocks all non-GET API requests.
A separate backend pytest covers real signed human session and PostgreSQL persistence.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
BASE = "http://127.0.0.1:3000"
TENANT = "11111111-1111-4111-8111-111111111111"
USER = "22222222-2222-4222-8222-222222222222"
STUDENT = "33333333-3333-4333-8333-333333333333"
CASE = "44444444-4444-4444-8444-444444444444"
NOW = "2026-11-06T15:00:00Z"


def response(path: str, page_path: str) -> object:
    if path.endswith("/org/me"):
        return {
            "tenant_id": TENANT, "user_id": USER, "role": "admin", "email": "visual@example.test",
            "display_name": "Equipe de permanência", "tenant_name": "Instituição de demonstração",
            "onboarding_completed": True,
            "operation_profile": "collection" if page_path == "/cobranca" else "institution",
            "enabled_modules": ["workspace", "permanence", "operations", "billing", "data", "mira_plan"],
            "permissions": [
                "dashboard.view", "students.view", "students.sensitive.view", "audit.view",
                "campaigns.view", "campaigns.create", "campaigns.edit", "campaigns.approve",
                "access.operator", "access.coordinator", "members.view", "data.view",
                *(["settings.manage"] if page_path == "/apps" else []),
            ],
            "features": {
                "academic_catalog": True, "academic_services": True, "academic_operations": True
            },
        }
    if page_path == "/apps":
        if path.endswith("/connectors"):
            return {"count": 3, "connectors": [
                {"id":"jacad","name":"JACAD","category":"academic"},
                {"id":"sponte","name":"Sponte","category":"academic"},
                {"id":"moodle","name":"Moodle","category":"academic"},
            ]}
        if path.endswith("/integrations/jacad"):
            return {"configured": True, "status":"connected", "enabled": True}
        if path.endswith("/integrations/sponte"):
            return {"configured": False, "status":"disconnected", "enabled": False}
        if path.endswith("/integrations/composio/catalog"):
            return {"source":"catalog_fixture", "total":4,"items":[
                {"slug":"gmail","name":"Gmail","enabled":True},
                {"slug":"outlook","name":"Outlook","enabled":False},
                {"slug":"slack","name":"Slack","enabled":False},
                {"slug":"googlecalendar","name":"Google Calendar","enabled":True},
            ]}
        if path.endswith("/integrations/composio/connections"):
            return {"total":2,"items":[
                {"id":"one","toolkit_slug":"gmail","status":"active","connected_account_id":"one"},
                {"id":"two","toolkit_slug":"slack","status":"revoked","connected_account_id":"two","disconnected_at":NOW},
            ]}
    if path.endswith("/org/workspaces"):
        return {"current_tenant_id": TENANT, "workspaces": []}
    if path.endswith("/org/members"):
        return {"members": []}
    if path.endswith("/object-views"):
        return {"views": []}
    if path.endswith("/agents/retention/campaigns/intelligence/proposals"):
        proposal = {
            "id": "66666666-6666-4666-8666-666666666666", "tenant_id": TENANT,
            "status": "draft", "title": "Proposta: Risco crítico",
            "source_group_ids": ["risk_critical"], "source_catalog_version": "1.0.0",
            "recommendation_engine": "signals-and-rules-v1", "source_evaluated_at": NOW,
            "objective": "Acolhimento prioritário", "strategy": "Contato humano e apoio acadêmico",
            "recommended_channels": ["email"], "cadence_days": [0, 3],
            "message_brief": "Rascunho institucional — não enviado",
            "audience_snapshot": [{
                "student_id": STUDENT, "matched_group_ids": ["risk_critical"],
                "eligible_channels": ["email"], "blocked_reasons": [],
                "internal_action_only": False,
            }],
            "audience_hash": "a" * 64, "audience_total": 1,
            "outreach_eligible_count": 1, "blocked_count": 0, "internal_action_count": 0,
            "created_by": USER, "created_at": NOW, "updated_at": NOW, "revision": 1,
            "reviewed_by": None, "reviewed_at": None, "approved_by": None, "approved_at": None,
            "authorization_status": "unverified", "authorization_basis": None,
            "authorization_reference": None, "authorization_attested_by": None,
            "authorization_attested_at": None, "scheduled_for": None, "schedule_timezone": None,
            "execution_enabled": False, "communication_authorization_status": "unverified",
            "authorization_review_required": True,
        }
        return {"count": 1, "proposals": [proposal]}
    if "campaigns" in path and "schedule" in path:
        return {"items": [], "count": 0, "schedules": []}
    if path.endswith("/work/activities/summary"):
        return {
            "pending": 1, "overdue": 0, "completed_7d": 0,
            "unassigned": 0, "campaign_pending": 0, "urgent_pending": 1, "as_of": NOW,
        }
    if path.endswith("/work/activities/priority-no-contact"):
        return {
            "as_of": NOW, "window_days": 7, "critical_total": 3,
            "contacted_7d": 1, "pending_verification": 1,
            "without_contact_7d": 1,
            "candidates": [{"id": STUDENT, "nome": "Aluno de exemplo", "matricula": "2026-001", "risk_score": 94}],
            "count_scope": "visual fixture", "policy": "synthetic data — not an operational count",
        }
    if path.endswith("/work/activities"):
        return {
            "count": 1,
            "activities": [{
                "id": "55555555-5555-4555-8555-555555555555", "tenant_id": TENANT,
                "student_id": STUDENT, "title": "Contatar aluno prioritário",
                "description": "Revisar contexto antes de uma abordagem humana.",
                "activity_type": "contact", "status": "open", "priority": "urgent",
                "origin_type": "manual", "campaign_id": None, "intervention_log_id": None,
                "assignee_user_id": USER, "assignee": {"id": USER, "display_name": "Equipe de permanência", "email": "visual@example.test"},
                "created_at": NOW, "updated_at": NOW, "due_at": None,
                "completed_at": None, "cancelled_at": None, "overdue": False
            }],
        }
    if path.endswith("/collections/cases"):
        return {
            "items": [{
                "id": CASE, "external_ref": "FIN-2026-001", "subject_type": "student",
                "subject_ref": "2026-001", "status": "open", "balance": "329.90",
                "source": "ERP acadêmico", "source_version": 1, "evidence_ref": "fixture",
                "verified_at": NOW, "updated_at": NOW
            }],
            "total": 1, "offset": 0, "limit": 50, "has_more": False,
        }
    if path.endswith("/risk/critical"):
        return {"students": [{
            "id": STUDENT, "nome": "Aluno de exemplo", "matricula": "2026-001",
            "curso": "Administração", "risk_score": 94, "risk_level": "critico",
        }]}
    if path.endswith("/risk/summary"):
        return {"summary": {"baixo": 0, "medio": 0, "critico": 3}, "total_students": 3, "total_scored": 3}
    if path.endswith("/agents/retention/work-summary"):
        return {"pending": 0, "overdue_48h": 0, "overdue_policy_hours": 48, "generated_at": NOW}
    if path.endswith("/agents/retention/logs"):
        return {"logs": [], "count": 0, "total": 0}
    if path.endswith("/students"):
        return {"students": [], "count": 0, "total": 0}
    return {"items": [], "students": [], "logs": [], "proposals": [], "events": [], "count": 0, "total": 0}


async def capture() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for route_path, heading, output in [
                ("/campanhas", "Campanhas inteligentes", "01-campanhas.png"),
                ("/trabalho", "Central de trabalho", "02-central-de-trabalho.png"),
                ("/cobranca", "Cobrança", "03-cobranca.png"),
                ("/apps", "Apps e integrações", "04-apps-integracoes.png"),
            ]:
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 960}, device_scale_factor=1, locale="pt-BR",
                    reduced_motion="reduce",
                )
                await context.add_init_script(
                    "window.localStorage.setItem('mira_access_token', 'visual-fixture-not-a-real-session');"
                )
                page = await context.new_page()
                problems = []

                async def mock_api(route):
                    method = route.request.method
                    if method == "OPTIONS":
                        await route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,OPTIONS"})
                        return
                    if method != "GET":
                        await route.fulfill(status=405, body="Visual fixture forbids mutations")
                        raise AssertionError("Unexpected mutating request in visual snapshot")
                    result = response(urlparse(route.request.url).path, route_path)
                    await route.fulfill(
                        status=200, content_type="application/json",
                        body=json.dumps(result, ensure_ascii=False),
                        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
                    )

                await page.route("**/api/v1/**", mock_api)
                page.on("pageerror", lambda exc: problems.append(str(exc)))
                await page.goto(BASE + route_path, wait_until="domcontentloaded", timeout=60000)
                await page.get_by_text(heading, exact=False).first.wait_for(timeout=30000)
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(ARTIFACTS / output), full_page=True, animations="disabled")
                if problems:
                    raise AssertionError(route_path + " browser exceptions: " + "; ".join(problems[:5]))
                print("Visual screenshot captured:", output)
                await context.close()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(capture())
