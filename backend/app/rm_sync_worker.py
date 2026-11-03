"""Standalone, graceful and tenant-allowlisted TOTVS RM sync worker."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import signal
import socket
from uuid import UUID

from app.db.session import AsyncSessionLocal, engine
from app.services.connectors.totvs_rm_sync_orchestrator import RMPostgresSyncQueue, RMSyncWorker


def _tenant_allowlist() -> tuple[str, ...]:
    values = tuple(
        value.strip() for value in os.environ.get("RM_SYNC_WORKER_TENANT_IDS", "").split(",")
        if value.strip()
    )
    if not values:
        raise RuntimeError("RM_SYNC_WORKER_TENANT_IDS deve listar os tenants autorizados.")
    try:
        normalized = tuple(str(UUID(value)) for value in values)
    except ValueError:
        raise RuntimeError("RM_SYNC_WORKER_TENANT_IDS contém UUID inválido.") from None
    if len(set(normalized)) != len(normalized):
        raise RuntimeError("RM_SYNC_WORKER_TENANT_IDS contém tenants duplicados.")
    return normalized


def load_executor():
    module_name = os.environ.get("RM_SYNC_EXECUTOR_MODULE", "").strip() or (
        "app.services.connectors.totvs_rm_executor"
    )
    try:
        module = importlib.import_module(module_name)
    except Exception:
        raise RuntimeError("Não foi possível carregar o módulo executor TOTVS RM configurado.") from None
    executor = getattr(module, "execute_rm_sync_job", None)
    if not callable(executor):
        raise RuntimeError("O módulo executor deve expor execute_rm_sync_job.")
    return executor


async def main(*, once: bool = False, poll_seconds: float = 2.0) -> None:
    if not 0.2 <= poll_seconds <= 60:
        raise ValueError("poll_seconds deve estar entre 0.2 e 60 segundos.")
    tenant_ids = _tenant_allowlist()
    executor = load_executor()
    if os.environ.get("RM_SYNC_EXECUTOR_MODULE", "").strip() in ("", "app.services.connectors.totvs_rm_executor"):
        if not os.environ.get("RM_SYNC_ALLOWED_HOSTS", "").strip():
            raise RuntimeError("RM_SYNC_ALLOWED_HOSTS deve listar os hosts RM autorizados.")
        if os.environ.get("RM_SYNC_ENABLE_EXECUTOR", "").lower() != "true":
            raise RuntimeError("RM_SYNC_ENABLE_EXECUTOR=true é obrigatório para iniciar o executor nativo.")
        if os.environ.get("RM_SYNC_EDUALUNODATA_CONTRACT_CONFIRMED", "").lower() != "true":
            raise RuntimeError("Homologue o contrato EduAlunoData/GetAll antes de iniciar o worker nativo.")
    worker = RMSyncWorker(
        RMPostgresSyncQueue(AsyncSessionLocal),
        executor,
        worker_id=f"{socket.gethostname()}:{os.getpid()}",
        tenant_ids=tenant_ids,
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    try:
        await worker.serve(once=once, poll_seconds=poll_seconds, stop_event=stop_event)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Worker durável TOTVS RM (read-only)")
    parser.add_argument("--once", action="store_true", help="Processa no máximo um job e encerra.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(main(once=args.once, poll_seconds=args.poll_seconds))
