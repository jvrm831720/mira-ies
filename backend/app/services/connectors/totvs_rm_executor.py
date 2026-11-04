"""Read-only TOTVS RM GetAll executor for the first validated roster contract.

Credentials are resolved at runtime by a trusted secret-provider module. They are
never accepted from job payloads, persisted in PostgreSQL, or written to logs.
"""
from __future__ import annotations

import importlib
import inspect
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.rm_sync import RmSyncScope
from app.services.connectors.totvs_rm_snapshot_repository import RMPostgresSnapshotRepository
from app.services.connectors.totvs_rm_snapshot_sync import RMSourceSyncContract, RMSnapshotScope
from app.services.connectors.totvs_rm_sync_orchestrator import RMJobCancelled, RMJobError, RMTransientJobError


@dataclass(frozen=True, slots=True)
class RMConnection:
    base_url: str
    username: str
    password: str = field(repr=False)
    context_headers: dict[str, str]


def _assert_executor_contract_enabled() -> None:
    if os.environ.get("RM_SYNC_ENABLE_EXECUTOR", "").lower() != "true":
        raise RMJobError("Executor TOTVS RM está desabilitado por configuração.")
    if os.environ.get("RM_SYNC_EDUALUNODATA_CONTRACT_CONFIRMED", "").lower() != "true":
        raise RMJobError("Contrato EduAlunoData/GetAll ainda não foi homologado para esta instalação.")


def _resolve_connection(tenant_id: str, coligada_id: str, source_name: str) -> RMConnection:
    provider_name = os.environ.get("RM_SYNC_CONNECTION_PROVIDER_MODULE", "app.services.connectors.totvs_rm_env_secret_provider").strip()
    if not provider_name:
        raise RMJobError("Secret provider TOTVS RM não configurado.")
    try:
        provider = importlib.import_module(provider_name)
        resolver = getattr(provider, "resolve_rm_connection", None)
        if not callable(resolver):
            raise RMJobError("Secret provider não implementa resolve_rm_connection.")
        raw = resolver(tenant_id=tenant_id, coligada_id=coligada_id, source_name=source_name)
    except RMJobError:
        raise
    except Exception:
        raise RMJobError("Não foi possível resolver a conexão TOTVS RM.") from None
    if inspect.isawaitable(raw):
        close = getattr(raw, "close", None)
        if callable(close):
            close()
        raise RMJobError("O secret provider deve expor resolve_rm_connection síncrono.")
    if not isinstance(raw, dict):
        raise RMJobError("Secret provider retornou configuração inválida.")
    base_url = str(raw.get("base_url") or "").strip()
    username = str(raw.get("username") or "")
    password = str(raw.get("password") or "")
    headers = raw.get("context_headers") or {}
    if not base_url or not username or not password or not isinstance(headers, dict):
        raise RMJobError("Conexão TOTVS RM incompleta.")
    return RMConnection(base_url, username, password, {str(k).upper(): str(v) for k, v in headers.items()})


def _validate_endpoint(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        raise RMJobError("URL base RM inválida.") from None
    allow_http = (
        os.environ.get("APP_ENV", "production").lower() == "development"
        and os.environ.get("RM_SYNC_ALLOW_INSECURE_HTTP", "").lower() == "true"
    )
    if parsed.scheme != "https" and not (allow_http and parsed.scheme == "http"):
        raise RMJobError("Conexão RM exige HTTPS.")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RMJobError("URL base RM inválida.")
    if port not in (None, 443, 80, 8051):
        raise RMJobError("Porta RM não autorizada.")
    allowed = {host.strip().lower() for host in os.environ.get("RM_SYNC_ALLOWED_HOSTS", "").split(",") if host.strip()}
    if not allowed or parsed.hostname.lower() not in allowed:
        raise RMJobError("Host RM não está na allowlist do worker.")
    return base_url.rstrip("/")


def _validate_context(headers: dict[str, str], coligada_id: str) -> dict[str, str]:
    allowed = {"CODCOLIGADA", "CODFILIAL", "CODTIPOCURSO", "CODSISTEMA"}
    if set(headers) - allowed:
        raise RMJobError("Secret provider retornou cabeçalhos de contexto não permitidos.")
    if headers.get("CODCOLIGADA") != coligada_id:
        raise RMJobError("CODCOLIGADA do contexto não corresponde ao job.")
    for value in headers.values():
        if not value or any(ord(char) < 32 for char in value):
            raise RMJobError("Cabeçalho de contexto RM inválido.")
    return headers


async def _read_page(client: httpx.AsyncClient, *, endpoint: str, offset: int, limit: int, max_bytes: int) -> list[dict]:
    chunks: list[bytes] = []
    total = 0
    try:
        async with client.stream("GET", endpoint, params={"start": offset, "limit": limit}) as response:
            if response.status_code in (408, 425, 429) or response.status_code >= 500:
                raise RMTransientJobError(f"RM respondeu HTTP {response.status_code}.")
            if response.status_code >= 400:
                raise RMJobError(f"RM rejeitou a consulta (HTTP {response.status_code}).")
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise RMJobError("Resposta RM excedeu o limite de tamanho configurado.")
                chunks.append(chunk)
    except (RMJobError, RMTransientJobError):
        raise
    except (httpx.TimeoutException, httpx.TransportError):
        raise RMTransientJobError("Falha de transporte ao consultar TOTVS RM.") from None
    try:
        payload = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RMJobError("RM retornou JSON inválido ou formato não homologado.") from None
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise RMJobError("GetAll deve retornar uma lista JSON de registros.")
    if len(payload) > limit:
        raise RMJobError("RM retornou mais registros que o limite solicitado.")
    return payload


def _normalize_roster_record(record: dict, coligada_id: str) -> dict:
    if str(record.get("CODCOLIGADA", "")).strip() != coligada_id:
        raise RMJobError("GetAll retornou registro de outra coligada.")
    ra = record.get("RA")
    if not isinstance(ra, str) or not ra.strip():
        raise RMJobError("RA deve ser retornado como texto para preservar zeros à esquerda.")
    # DataServer can return additional personal fields; persist only the approved roster key.
    return {
        "CODCOLIGADA": str(record["CODCOLIGADA"]).strip(),
        "RA": ra.strip(),
    }


async def execute_rm_sync_job(job, heartbeat, cancelled, attach_snapshot, before_publish):
    """Execute a read-only, allowlisted EduAlunoData full snapshot."""
    tenant_id = job["tenant_id"]
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
        scope = (await session.execute(select(RmSyncScope).where(
            RmSyncScope.id == job["scope_id"], RmSyncScope.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if scope is None:
            raise RMJobError("Escopo RM não encontrado no tenant do job.")
        scope_data = {
            "coligada_id": scope.coligada_id, "source_name": scope.source_name,
            "entity_name": scope.entity_name, "schema_version": scope.schema_version,
        }

    _assert_executor_contract_enabled()
    # Other DataServers need their own validated identity and response contracts.
    if scope_data["source_name"] != "TOTVS_RM":
        raise RMJobError("source_name deve ser TOTVS_RM para o executor nativo.")
    if scope_data["entity_name"] != "EduAlunoData":
        raise RMJobError("Executor nativo homologado somente para EduAlunoData nesta wave.")
    if (job.get("request") or {}).get("mode") != "full_snapshot":
        raise RMJobError("Executor nativo aceita somente full_snapshot.")
    coligada_id = scope_data["coligada_id"]
    connection = _resolve_connection(tenant_id, coligada_id, scope_data["source_name"])
    endpoint = f"{_validate_endpoint(connection.base_url)}/rest/EduAlunoData"
    context = _validate_context(connection.context_headers, coligada_id)
    page_size = int((job.get("request") or {}).get("page_size", 500))
    if not 1 <= page_size <= 1000:
        raise RMJobError("page_size fora do intervalo permitido.")

    contract = RMSourceSyncContract(
        source_name=scope_data["source_name"], entity_name="EduAlunoData",
        identity_fields=("CODCOLIGADA", "RA"), coligada_field="CODCOLIGADA",
        supports_full_snapshot=True, supports_incremental=False,
        deletion_semantics_confirmed=False,
    )
    snapshot_scope = RMSnapshotScope(
        tenant_id=tenant_id, coligada_id=coligada_id,
        source_name=scope_data["source_name"], entity_name="EduAlunoData",
        schema_version=scope_data["schema_version"],
    )
    repository = RMPostgresSnapshotRepository()
    run_id = job.get("snapshot_run_id")
    if not run_id:
        from uuid import NAMESPACE_URL, uuid5
        run_id = str(uuid5(NAMESPACE_URL, f"mira:totvs-rm-job:{job['id']}"))
        async with AsyncSessionLocal() as session:
            await repository.begin_run(session, run_id=run_id, scope=snapshot_scope, contract=contract)
        await attach_snapshot(run_id)
    async with AsyncSessionLocal() as session:
        checkpoint = await repository.get_checkpoint(session, tenant_id=tenant_id, run_id=run_id)
    if not checkpoint:
        raise RMJobError("Checkpoint não encontrado no tenant do job.")
    if checkpoint["status"] == "committed":
        if not await before_publish():
            raise RMJobCancelled()
        return {"snapshot_run_id": run_id}
    if checkpoint["status"] != "staging":
        raise RMJobError("Checkpoint não está em staging; execução não pode ser retomada.")
    offset = checkpoint["next_offset"]
    max_bytes = int(os.environ.get("RM_SYNC_MAX_RESPONSE_BYTES", str(8 * 1024 * 1024)))
    timeout = httpx.Timeout(
        connect=float(os.environ.get("RM_SYNC_CONNECT_TIMEOUT_SECONDS", "10")),
        read=float(os.environ.get("RM_SYNC_READ_TIMEOUT_SECONDS", "60")),
        write=10.0, pool=10.0,
    )
    auth = httpx.BasicAuth(connection.username, connection.password)
    headers = {"Accept": "application/json", **context}
    try:
        async with httpx.AsyncClient(
            auth=auth, headers=headers, timeout=timeout,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            follow_redirects=False, verify=True, trust_env=False,
        ) as client:
            while True:
                if await cancelled():
                    raise RMJobCancelled()
                if not await heartbeat():
                    if await cancelled():
                        raise RMJobCancelled()
                    raise RMTransientJobError("Lease do worker não está mais válida.")
                page = await _read_page(
                    client, endpoint=endpoint, offset=offset, limit=page_size, max_bytes=max_bytes,
                )
                page = [_normalize_roster_record(record, coligada_id) for record in page]
                has_more = len(page) == page_size
                next_offset = offset + len(page)
                async with AsyncSessionLocal() as session:
                    await repository.stage_page(
                        session, tenant_id=tenant_id, run_id=run_id,
                        offset=offset, next_offset=next_offset, records=page, has_more=has_more,
                    )
                offset = next_offset
                if not has_more:
                    break
            if await cancelled() or not await before_publish():
                raise RMJobCancelled()
            async with AsyncSessionLocal() as session:
                await repository.finalize_run(
                    session, tenant_id=tenant_id, run_id=run_id,
                    expected_record_count=None, authoritative_full_snapshot=False,
                    job_id=job["id"], worker_id=job["worker_id"],
                )
    except RMJobCancelled:
        await repository.abort_run(tenant_id=tenant_id, run_id=run_id, reason="cancelled")
        raise
    return {"snapshot_run_id": run_id}
