"""
Conectores LMS — engajamento digital (AVA).

Documento do MVP: Moodle e Canvas via API / webhooks.
"""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from app.services.connectors.base import (
    ConnectorInfo,
    pick,
    to_int,
    to_float,
    to_str,
)


def _as_list(payload: Any) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "users", "students", "items", "results", "events"):
            if key in payload and isinstance(payload[key], list):
                return [x for x in payload[key] if isinstance(x, dict)]
        return [payload]
    return []


def _days_since(ts: Any) -> int | None:
    if ts is None or ts == "":
        return None
    try:
        if isinstance(ts, (int, float)):
            ts_val = float(ts)
            if ts_val > 1e12:
                ts_val = ts_val / 1000.0
            last = datetime.fromtimestamp(ts_val, tz=timezone.utc)
        else:
            s = str(ts).replace("Z", "+00:00")
            last = datetime.fromisoformat(s)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        return max(0, delta.days)
    except Exception:
        return None


class MoodleConnector:
    info = ConnectorInfo(
        id="moodle",
        name="Moodle",
        category="lms",
        description="Cliente nativo read-only para Moodle Web Services REST; funções disponíveis dependem do serviço externo configurado na instituição.",
        has_api=True,
        endpoints=[
            "POST /webservice/rest/server.php (core_webservice_get_site_info)",
            "POST /webservice/rest/server.php (core_user_get_users_by_field)",
            "POST /webservice/rest/server.php (core_enrol_get_users_courses)",
            "POST /webservice/rest/server.php (core_completion_get_activities_completion_status)",
            "POST /api/v1/connectors/moodle/engagement",
            "POST /api/v1/webhooks/moodle",
        ],
        sample_fields=[
            "id", "username", "fullname", "lastaccess", "courses",
            "completion_pct", "assignments_pending",
        ],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            matricula = to_str(pick(
                item, "idnumber", "username", "id", "userid", "matricula", "user_id"
            ))
            nome = to_str(pick(
                item, "fullname", "name", "nome", "firstname"
            ))
            if not nome:
                first = to_str(pick(item, "firstname", "first_name"), "")
                last = to_str(pick(item, "lastname", "last_name"), "")
                nome = f"{first} {last}".strip() or None

            if not matricula or not nome:
                continue

            dias_login = to_int(pick(item, "dias_sem_login", "days_since_login"))
            if dias_login is None:
                dias_login = _days_since(pick(item, "lastaccess", "last_access", "timecreated"))

            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "course", "coursename", "course_name", "curso")),
                "turma": to_str(pick(item, "group", "turma", "section")),
                "semestre": to_int(pick(item, "semester", "semestre")),
                "forma_ingresso": None,
                "telefone": to_str(pick(item, "phone1", "phone2", "phone", "mobile", "telefone", "celular")),
                "email": to_str(pick(item, "email", "emailaddress", "e_mail")),
                "dias_atraso_boleto": None,
                "recorrencia_atrasos": None,
                "dias_sem_login": dias_login,
                "presenca_percentual": to_float(pick(
                    item, "completion_pct", "completion", "progress", "presenca"
                )),
                "nota_media": to_float(pick(item, "grade", "grade_avg", "nota", "finalgrade")),
                "reprovacoes": to_int(pick(item, "failed_activities", "reprovacoes")),
                "source_id": "moodle",
                "raw": item,
            })
        return records


class CanvasConnector:
    info = ConnectorInfo(
        id="canvas",
        name="Canvas",
        category="lms",
        description="LMS Instructure. API REST + webhooks de enrollment e submissions.",
        has_api=True,
        endpoints=[
            "POST /api/v1/connectors/canvas/engagement",
            "POST /api/v1/webhooks/canvas",
        ],
        sample_fields=[
            "id", "sis_user_id", "name", "last_activity_at",
            "enrollments", "current_score",
        ],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            if "body" in item and isinstance(item["body"], dict):
                item = {**item, **item["body"]}

            matricula = to_str(pick(
                item, "sis_user_id", "user_id", "id", "matricula"
            ))
            nome = to_str(pick(item, "name", "user_name", "nome", "sortable_name"))
            if not matricula or not nome:
                continue
            user = item.get("user") if isinstance(item.get("user"), dict) else {}

            dias_login = to_int(pick(item, "dias_sem_login"))
            if dias_login is None:
                dias_login = _days_since(pick(
                    item, "last_activity_at", "last_login", "updated_at"
                ))

            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "course_name", "course", "curso")),
                "turma": to_str(pick(item, "section_name", "section", "turma")),
                "semestre": to_int(pick(item, "term", "semestre")),
                "forma_ingresso": None,
                "telefone": to_str(
                    pick(item, "phone", "phone_number", "mobile", "telefone", "celular")
                    or pick(user, "phone", "phone_number", "mobile", "telefone")
                ),
                "email": to_str(
                    pick(item, "email", "email_address", "e_mail")
                    or pick(user, "email", "email_address")
                ),
                "dias_atraso_boleto": None,
                "recorrencia_atrasos": None,
                "dias_sem_login": dias_login,
                "presenca_percentual": to_float(pick(
                    item, "completion", "progress", "presenca"
                )),
                "nota_media": to_float(pick(
                    item, "current_score", "final_score", "score", "nota_media"
                )),
                "reprovacoes": to_int(pick(item, "missing_submissions", "reprovacoes")),
                "source_id": "canvas",
                "raw": item,
            })
        for r in records:
            if r.get("nota_media") is not None and r["nota_media"] > 10:
                r["nota_media"] = round(r["nota_media"] / 10.0, 2)
        return records
