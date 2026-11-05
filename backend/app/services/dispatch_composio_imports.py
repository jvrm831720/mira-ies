"""Composio -> MIRA Dispatch: bounded, tenant-owned read execution + normalized staging.

This is a real Composio session execution path, not an SDK stub. Only tools
explicitly allowlisted for read ingestion can run; no sender is invoked here.
Tool results remain untrusted until they pass local mapping/validation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.composio_connection import TenantComposioAccount, TenantComposioSession
from app.services.composio.client import get_composio_client
from app.services.composio.connections import _verify_remote_account
from app.services.composio.policy import _tool_schema, _validate_schema_value
from app.services.dispatch_core import audit, bind_tenant
from app.services.dispatch_sources import require_source, source_tool_is_read_only

_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_DENIED_FIELDS = re.compile(r"password|token|secret|credential|api_key|private_key", re.I)
_MAX_ROWS = 100
_MAX_BYTES = 256 * 1024
_MAX_VALUE = 2000
_TIMEOUT_SECONDS = 25


class ComposioIngestDenied(ValueError):
    """Policy, response or mapping rejected; never include sensitive result data."""


def _require_enabled() -> None:
    settings = get_settings()
    if not (
        settings.dispatch_composio_ingestion_enabled
        and settings.composio_enabled
        and settings.composio_api_key
        and settings.composio_identity_secret
    ):
        raise ComposioIngestDenied("Execução Composio para ingestão está desabilitada.")
    if not settings.dispatch_composio_ingestion_read_tools.strip():
        raise ComposioIngestDenied("Configure explicitamente a allowlist de leitura.")


def _tool_allowed(slug: str) -> bool:
    settings = get_settings()
    allowed = {
        item.strip().upper()
        for item in settings.dispatch_composio_ingestion_read_tools.split(",")
        if item.strip()
    }
    return source_tool_is_read_only(slug) and slug.upper() in allowed


def _path_parts(path: str) -> list[str]:
    if not isinstance(path, str) or len(path) > 240:
        raise ComposioIngestDenied("Caminho de dados inválido.")
    parts = path.split(".") if path else []
    if len(parts) > 6 or any(not _FIELD.fullmatch(part) for part in parts):
        raise ComposioIngestDenied("Caminho de dados inválido.")
    return parts


def _pick(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in _path_parts(path):
        if not isinstance(current, dict) or part not in current:
            raise ComposioIngestDenied("Caminho de campo ausente na resposta.")
        current = current[part]
    return current


def _records(data: Any, path: str) -> list[dict[str, Any]]:
    current = data
    if path:
        if not isinstance(current, dict):
            raise ComposioIngestDenied("Resposta não é um objeto para o caminho escolhido.")
        current = _pick(current, path)
    elif isinstance(current, dict):
        # Only unambiguous well-known envelopes; never guess arbitrary nested lists.
        for candidate in ("items", "records", "results"):
            if isinstance(current.get(candidate), list):
                current = current[candidate]
                break
        else:
            raise ComposioIngestDenied("Informe o caminho da lista no resultado Composio.")
    if not isinstance(current, list) or len(current) > _MAX_ROWS:
        raise ComposioIngestDenied("A ferramenta deve devolver uma lista com até 100 registros.")
    if any(not isinstance(row, dict) for row in current):
        raise ComposioIngestDenied("A origem retornou um item sem estrutura de registro.")
    return current


def _as_small_string(value: Any, *, maximum: int = _MAX_VALUE) -> str:
    if value is None or isinstance(value, (list, dict)):
        raise ComposioIngestDenied("Campos mapeados devem conter valores escalares.")
    if isinstance(value, float) and (value != value or abs(value) == float("inf")):
        raise ComposioIngestDenied("Campo numérico não finito.")
    result = str(value).strip()
    if not result or len(result) > maximum:
        raise ComposioIngestDenied("Campo mapeado vazio ou acima do limite.")
    return result


def normalize_rows(
    data: Any, *, rows_path: str, record_id_field: str, subject_ref_field: str,
    subject_type: str, record_type: str, field_map: dict[str, str],
) -> list[dict[str, Any]]:
    if subject_type not in {"student", "external"}:
        raise ComposioIngestDenied("Tipo de destinatário inválido.")
    if record_type not in {"contact", "obligation", "generic"}:
        raise ComposioIngestDenied("Tipo de registro inválido.")
    if len(field_map) > 12 or any(
        not _FIELD.fullmatch(key) or _DENIED_FIELDS.search(key)
        for key in field_map
    ):
        raise ComposioIngestDenied("Mapeamento contém campos não permitidos.")
    _path_parts(record_id_field)
    _path_parts(subject_ref_field)
    for path in field_map.values():
        _path_parts(path)
    rows = _records(data, rows_path)
    normalized = []
    keys = set()
    for row in rows:
        rid = _as_small_string(_pick(row, record_id_field), maximum=160)
        subject = _as_small_string(_pick(row, subject_ref_field), maximum=160)
        if rid in keys:
            raise ComposioIngestDenied("IDs duplicados no lote retornado pela ferramenta.")
        keys.add(rid)
        mapped = {
            key: _as_small_string(_pick(row, value))
            for key, value in field_map.items()
        }
        # Student identifiers must be stable MIRA UUIDs; no fuzzy matching.
        if subject_type == "student":
            from uuid import UUID
            try:
                subject = str(UUID(subject))
            except ValueError as exc:
                raise ComposioIngestDenied("O ID de aluno deve ser um UUID MIRA.") from exc
        normalized.append({
            "source_record_id": rid, "subject_ref": subject,
            "subject_type": subject_type, "record_type": record_type,
            "values": mapped,
        })
    return normalized


def _execute_single_read(
    *, user_id: str, account_id: str, toolkit: str,
    tool_slug: str, arguments: dict[str, Any],
) -> Any:
    """Called from a bounded worker thread; never use unrestricted sessions."""
    client = get_composio_client()
    session = client.sessions.create(
        user_id=user_id,
        toolkits=[toolkit],
        tools={toolkit: {"enable": [tool_slug]}},
        connected_accounts={toolkit: [account_id]},
        manage_connections={"enable": False},
        sandbox={"enable": False},
    )
    result = session.execute(tool_slug, arguments=arguments, account=account_id)
    state = getattr(result, "result_type", None)
    if state is None and isinstance(result, dict):
        state = result.get("result_type")
    if str(state).lower() != "completed":
        raise ComposioIngestDenied("Composio não confirmou sucesso na leitura.")
    data = getattr(result, "data", None)
    if isinstance(result, dict):
        data = result.get("data", data)
    if data is None:
        raise ComposioIngestDenied("Composio não retornou dados.")
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    try:
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ComposioIngestDenied("Resposta incompatível com o contrato de dados.") from exc
    if len(raw.encode("utf-8")) > _MAX_BYTES:
        raise ComposioIngestDenied("Resposta acima do limite de 256 KB por leitura.")
    return data


def _encrypt_values(data: dict[str, Any]) -> str:
    key = get_settings().dispatch_composio_data_key
    if not key:
        raise ComposioIngestDenied("Chave de criptografia de observações não configurada.")
    try:
        return Fernet(key.encode()).encrypt(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).decode()
    except (ValueError, TypeError) as exc:
        raise ComposioIngestDenied("Chave de observações inválida.") from exc


def _fingerprint(data: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


async def _context(
    db: AsyncSession, *, tenant_id: str, account_id: str, tool_slug: str,
) -> tuple[str, str]:
    _require_enabled()
    tool = tool_slug.strip().upper()
    if not _tool_allowed(tool):
        raise ComposioIngestDenied("Ferramenta não permitida para ingestão somente leitura.")
    source = await require_source(
        db, tenant_id=tenant_id, kind="composio",
        reference=account_id, tool_slug=tool,
    )
    if not source.available:
        raise ComposioIngestDenied(f"Conexão ou política não autorizada: {source.reason}")
    account = (await db.execute(select(TenantComposioAccount).where(
        TenantComposioAccount.tenant_id == tenant_id,
        TenantComposioAccount.connected_account_id == account_id,
    ))).scalar_one()
    session = (await db.execute(select(TenantComposioSession).where(
        TenantComposioSession.tenant_id == tenant_id,
        TenantComposioSession.status != "disabled",
    ))).scalar_one_or_none()
    if session is None:
        raise ComposioIngestDenied("Identidade Composio da organização não encontrada.")
    return account.toolkit_slug, session.composio_user_id


async def import_read_tool(
    db: AsyncSession, *, tenant_id: str, actor_id: str, account_id: str,
    tool_slug: str, arguments: dict[str, Any], rows_path: str,
    record_id_field: str, subject_ref_field: str, subject_type: str,
    record_type: str, field_map: dict[str, str], idempotency_key: str,
) -> dict[str, Any]:
    """Fetch from Composio and stage encrypted records; no consent or sending."""
    await bind_tenant(db, tenant_id)
    toolkit, composio_user = await _context(
        db, tenant_id=tenant_id, account_id=account_id, tool_slug=tool_slug,
    )
    _path_parts(rows_path)
    _path_parts(record_id_field)
    _path_parts(subject_ref_field)
    for item in field_map.values():
        _path_parts(item)
    if not get_settings().dispatch_composio_data_key:
        raise ComposioIngestDenied("A chave de criptografia de dados não foi configurada.")
    if not 16 <= len(idempotency_key) <= 120:
        raise ComposioIngestDenied("Chave idempotente inválida.")
    if len(json.dumps(arguments, allow_nan=False)) > 16000:
        raise ComposioIngestDenied("Argumentos da ferramenta excedem o limite.")
    # Schema is fetched live; supported JSON-schema subset fails closed.
    schema = await run_in_threadpool(_tool_schema, toolkit, tool_slug)
    _validate_schema_value(arguments, schema)
    request_hash = _fingerprint({
        "account": account_id, "tool": tool_slug.upper(),
        "arguments": arguments, "path": rows_path, "id": record_id_field,
        "subject": subject_ref_field, "subject_type": subject_type,
        "record_type": record_type, "fields": field_map,
    })
    lock = f"dispatch:composio:import:{tenant_id}:{idempotency_key}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": lock})
    previous = (await db.execute(text("""
        SELECT id, status, request_hash, rows_total, rows_created, rows_updated
        FROM dispatch_source_import_runs
        WHERE tenant_id=:tenant AND idempotency_key=:key
    """), {"tenant": tenant_id, "key": idempotency_key})).mappings().first()
    if previous is not None:
        if previous["request_hash"] != request_hash:
            raise ComposioIngestDenied("Idempotency-Key já usada em uma importação diferente.")
        if previous["status"] == "succeeded":
            return {
                "run_id": str(previous["id"]), "status": "succeeded",
                "total": previous["rows_total"],
                "created": previous["rows_created"],
                "updated": previous["rows_updated"], "deduplicated": True,
            }
        raise ComposioIngestDenied("Importação já registrada; revise o resultado antes de reenviar.")
    # Bound remote API spend per workspace. The transaction-scoped lock
    # serializes the quota check across different Idempotency-Keys.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"dispatch:composio:hourly:{tenant_id}"},
    )
    recent = (await db.execute(text("""
        SELECT count(*) FROM dispatch_source_import_runs
        WHERE tenant_id=:tenant AND started_at>=now()-interval '1 hour'
    """), {"tenant": tenant_id})).scalar_one()
    if recent >= 60:
        raise ComposioIngestDenied("Limite de 60 consultas Composio por hora por organização atingido.")
    run_id = str(uuid4())
    await db.execute(text("""
        INSERT INTO dispatch_source_import_runs (
          id, tenant_id, connected_account_id, toolkit_slug, tool_slug,
          actor_id, idempotency_key, request_hash, status
        ) VALUES (
          :id,:tenant,:account,:toolkit,:tool,:actor,:key,:hash,'running'
        )
    """), {
        "id": run_id, "tenant": tenant_id, "account": account_id,
        "toolkit": toolkit, "tool": tool_slug.upper(), "actor": actor_id,
        "key": idempotency_key, "hash": request_hash,
    })
    await db.commit()

    try:
        # Remote account ownership is revalidated with Composio (not only DB state).
        await asyncio.wait_for(
            asyncio.to_thread(
                _verify_remote_account,
                connected_account_id=account_id,
                expected_user_id=composio_user, expected_toolkit=toolkit,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
        remote_data = await asyncio.wait_for(
            asyncio.to_thread(
                _execute_single_read,
                user_id=composio_user, account_id=account_id,
                toolkit=toolkit, tool_slug=tool_slug.upper(), arguments=arguments,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
        rows = normalize_rows(
            remote_data, rows_path=rows_path,
            record_id_field=record_id_field,
            subject_ref_field=subject_ref_field,
            subject_type=subject_type, record_type=record_type,
            field_map=field_map,
        )
        # No raw provider result or credentials enter audit logs or HTTP output.
        await bind_tenant(db, tenant_id)
        # An admin may revoke the account/policy while the network call is running.
        await _context(db, tenant_id=tenant_id, account_id=account_id, tool_slug=tool_slug)
        created = updated = 0
        await db.execute(text("""
            SELECT id FROM dispatch_source_import_runs
            WHERE tenant_id=:tenant AND id=:run AND status='running' FOR UPDATE
        """), {"tenant": tenant_id, "run": run_id})
        for item in sorted(rows, key=lambda row: row["source_record_id"]):
            ciphertext = _encrypt_values(item["values"])
            digest = _fingerprint(item)
            # A consistent record-level advisory lock prevents concurrent
            # overlapping syncs from racing over source versions.
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": (
                    f"dispatch:observation:{tenant_id}:{account_id}:"
                    f"{tool_slug.upper()}:{item['source_record_id']}"
                )},
            )
            existing = (await db.execute(text("""
                SELECT payload_hash FROM dispatch_source_observations
                WHERE tenant_id=:tenant AND connected_account_id=:account
                  AND tool_slug=:tool AND source_record_id=:record FOR UPDATE
            """), {
                "tenant": tenant_id, "account": account_id,
                "tool": tool_slug.upper(), "record": item["source_record_id"],
            })).scalar_one_or_none()
            args = {
                "id": str(uuid4()), "tenant": tenant_id,
                "account": account_id, "toolkit": toolkit,
                "tool": tool_slug.upper(), "record": item["source_record_id"],
                "kind": item["subject_type"], "subject": item["subject_ref"],
                "type": record_type, "cipher": ciphertext, "hash": digest,
            }
            if existing is None:
                await db.execute(text("""
                    INSERT INTO dispatch_source_observations (
                      id,tenant_id,connected_account_id,toolkit_slug,tool_slug,
                      source_record_id,subject_type,subject_ref,record_type,
                      payload_ciphertext,payload_hash
                    ) VALUES (
                      :id,:tenant,:account,:toolkit,:tool,:record,:kind,:subject,:type,:cipher,:hash
                    )
                """), args)
                created += 1
            elif existing != digest:
                await db.execute(text("""
                    UPDATE dispatch_source_observations
                    SET subject_type=:kind,subject_ref=:subject,record_type=:type,
                        payload_ciphertext=:cipher,payload_hash=:hash,
                        source_version=source_version+1,
                        observed_at=now(),updated_at=now()
                    WHERE tenant_id=:tenant AND connected_account_id=:account
                      AND tool_slug=:tool AND source_record_id=:record
                """), args)
                updated += 1
            else:
                # Even unchanged source records receive a fresh observation
                # timestamp, without rewriting their encrypted payload/version.
                await db.execute(text("""
                    UPDATE dispatch_source_observations
                    SET observed_at=now(),updated_at=now()
                    WHERE tenant_id=:tenant AND connected_account_id=:account
                      AND tool_slug=:tool AND source_record_id=:record
                """), args)
        await db.execute(text("""
            UPDATE dispatch_source_import_runs
            SET status='succeeded',rows_total=:total,
                rows_created=:created,rows_updated=:updated,finished_at=now()
            WHERE tenant_id=:tenant AND id=:id AND status='running'
        """), {
            "tenant": tenant_id, "id": run_id, "total": len(rows),
            "created": created, "updated": updated,
        })
        await audit(db, tenant_id=tenant_id,
                    event_type="source.composio_read_imported",
                    details={"toolkit": toolkit, "tool": tool_slug.upper(),
                             "total": len(rows), "created": created,
                             "updated": updated, "run_id": run_id})
        await db.commit()
        return {
            "run_id": run_id, "status": "succeeded", "total": len(rows),
            "created": created, "updated": updated, "deduplicated": False,
            "contact_authorization": "not_inferred",
            "financial_authority": "not_inferred",
        }
    except Exception as exc:
        await db.rollback()
        await bind_tenant(db, tenant_id)
        await db.execute(text("""
            UPDATE dispatch_source_import_runs
            SET status='failed',error_code=:code,finished_at=now()
            WHERE tenant_id=:tenant AND id=:id AND status='running'
        """), {"tenant": tenant_id, "id": run_id, "code": type(exc).__name__[:80]})
        await db.commit()
        if isinstance(exc, ComposioIngestDenied):
            raise
        raise ComposioIngestDenied(
            "Leitura Composio não concluída. Nenhum contato foi liberado para envio."
        ) from exc


def _decrypt_values(ciphertext: str) -> dict[str, Any]:
    from cryptography.fernet import InvalidToken
    key = get_settings().dispatch_composio_data_key
    if not key:
        raise ComposioIngestDenied("Chave de criptografia indisponível.")
    try:
        value = json.loads(Fernet(key.encode()).decrypt(ciphertext.encode()).decode())
    except (ValueError, TypeError, InvalidToken, json.JSONDecodeError) as exc:
        raise ComposioIngestDenied("Observação de origem corrompida ou não autenticada.") from exc
    if not isinstance(value, dict):
        raise ComposioIngestDenied("Observação com estrutura inválida.")
    return value


async def stage_authorized_observations(
    db: AsyncSession, *, tenant_id: str, actor_id: str,
    campaign_id: str, source_record_ids: list[str],
) -> dict[str, int]:
    """Select imported Composio subjects into a DRAFT outbox, never grant consent.

    Only existing MIRA authorizations, destinations, and debt facts can become
    actionable dispatch items. Imported provider values never create them.
    """
    from app.services.dispatch_core import enqueue_recipients, get_campaign
    await bind_tenant(db, tenant_id)
    campaign = await get_campaign(
        db, tenant_id=tenant_id, campaign_id=campaign_id, lock=True,
    )
    if campaign is None:
        raise LookupError("Campanha não encontrada.")
    if campaign["status"] != "draft" or campaign["source_kind"] != "composio":
        raise ComposioIngestDenied("A campanha deve ser um rascunho vinculado ao Composio.")
    account_id = campaign["source_ref"]
    tool_slug = campaign["source_tool_slug"]
    await _context(db, tenant_id=tenant_id, account_id=account_id, tool_slug=tool_slug)
    if len(source_record_ids) > _MAX_ROWS or any(
        not isinstance(item, str) or not 1 <= len(item) <= 160
        for item in source_record_ids
    ):
        raise ComposioIngestDenied("Identificadores de registros fora dos limites.")
    if len(set(source_record_ids)) != len(source_record_ids):
        raise ComposioIngestDenied("Registros repetidos na seleção.")
    sql = """
        SELECT source_record_id,subject_type,subject_ref,record_type,payload_ciphertext
        FROM dispatch_source_observations
        WHERE tenant_id=:tenant AND connected_account_id=:account AND tool_slug=:tool
          AND observed_at>=now()-interval '24 hours'
    """
    params: dict[str, Any] = {
        "tenant": tenant_id, "account": account_id, "tool": tool_slug,
    }
    if source_record_ids:
        sql += " AND source_record_id = ANY(CAST(:ids AS text[]))"
        params["ids"] = source_record_ids
    sql += " ORDER BY observed_at DESC LIMIT 100"
    observations = (await db.execute(text(sql), params)).mappings().all()
    if source_record_ids and len(observations) != len(source_record_ids):
        raise ComposioIngestDenied("Um ou mais registros não existem nesta conexão.")

    from app.core.config import get_settings
    sources = [
        item.strip() for item in get_settings().dispatch_trusted_authorization_sources.split(",")
        if item.strip()
    ]
    if not sources or not observations:
        return {"created": 0, "duplicates": 0, "filtered": len(observations)}

    selected: list[dict[str, Any]] = []
    filtered = 0
    for observation in observations:
        subject_type = observation["subject_type"]
        subject_ref = observation["subject_ref"]
        authorized = (await db.execute(text("""
            SELECT evidence_ref FROM dispatch_authorizations
            WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
              AND channel=:channel AND purpose=:purpose AND status='granted'
              AND source=ANY(CAST(:sources AS text[]))
              AND verified_at >= now()-interval '90 days' AND expires_at>now()
        """), {
            "tenant": tenant_id, "kind": subject_type,
            "ref": subject_ref, "channel": campaign["channel"],
            "purpose": campaign["purpose"], "sources": sources,
        })).scalar_one_or_none()
        if not authorized:
            filtered += 1
            continue
        if campaign["purpose"] == "collections" and observation["record_type"] != "obligation":
            filtered += 1
            continue
        values = _decrypt_values(observation["payload_ciphertext"])
        obligation_ref = values.get("obligation_ref")
        if campaign["purpose"] == "collections":
            if not isinstance(obligation_ref, str) or not 1 <= len(obligation_ref) <= 160:
                filtered += 1
                continue
            existing = (await db.execute(text("""
                SELECT 1 FROM dispatch_obligations WHERE
                tenant_id=:tenant AND external_ref=:obligation
                AND subject_type=:kind AND subject_ref=:subject
                AND status='open' AND balance>0
            """), {
                "tenant": tenant_id, "obligation": obligation_ref,
                "kind": subject_type, "subject": subject_ref,
            })).first()
            if not existing:
                filtered += 1
                continue
        else:
            obligation_ref = None
        # Do not trust the imported address itself. MIRA's independently
        # verified destination/contact must already be in the workspace.
        if subject_type == "student":
            contact = (await db.execute(text("""
                SELECT 1 FROM students
                WHERE tenant_id=:tenant AND id::text=:id AND is_active IS TRUE
                  AND communication_opt_out IS FALSE
            """), {"tenant": tenant_id, "id": subject_ref})).first()
        else:
            contact = (await db.execute(text("""
                SELECT 1 FROM dispatch_external_contacts
                WHERE tenant_id=:tenant AND subject_ref=:ref AND channel=:channel
                  AND consent_ref=:consent AND opt_out IS FALSE
            """), {
                "tenant": tenant_id, "ref": subject_ref,
                "channel": campaign["channel"], "consent": authorized,
            })).first()
        if not contact:
            filtered += 1
            continue
        suppressed = (await db.execute(text("""
            SELECT 1 FROM dispatch_suppressions
            WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
              AND channel IN ('all',:channel)
        """), {
            "tenant": tenant_id, "kind": subject_type,
            "ref": subject_ref, "channel": campaign["channel"],
        })).first()
        if suppressed:
            filtered += 1
            continue
        selected.append({
            "subject_type": subject_type, "subject_ref": subject_ref,
            "consent_ref": authorized, "obligation_ref": obligation_ref,
        })
    if not selected:
        return {"created": 0, "duplicates": 0, "filtered": filtered}
    result = await enqueue_recipients(
        db, tenant_id=tenant_id, campaign_id=campaign_id,
        targets=selected, actor=actor_id,
    )
    return {**result, "filtered": filtered}


async def list_import_runs(
    db: AsyncSession, *, tenant_id: str, limit: int = 30,
) -> list[dict[str, Any]]:
    await bind_tenant(db, tenant_id)
    result = await db.execute(text("""
        SELECT id,toolkit_slug,tool_slug,status,rows_total,rows_created,
               rows_updated,started_at,finished_at,error_code
        FROM dispatch_source_import_runs
        WHERE tenant_id=:tenant ORDER BY started_at DESC LIMIT :limit
    """), {"tenant": tenant_id, "limit": limit})
    return [dict(row) for row in result.mappings().all()]


async def list_observation_counts(db: AsyncSession, *, tenant_id: str) -> list[dict[str, Any]]:
    await bind_tenant(db, tenant_id)
    result = await db.execute(text("""
        SELECT toolkit_slug, tool_slug, record_type, count(*) AS records,
               max(observed_at) AS last_observed_at
        FROM dispatch_source_observations
        WHERE tenant_id=:tenant
        GROUP BY toolkit_slug,tool_slug,record_type ORDER BY last_observed_at DESC
        LIMIT 100
    """), {"tenant": tenant_id})
    return [dict(row) for row in result.mappings().all()]
