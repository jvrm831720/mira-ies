"""Standalone worker for the durable TOTVS RM synchronization queue.

Set RM_SYNC_EXECUTOR_MODULE to a trusted module exposing async
execute_rm_sync_job(job, heartbeat, cancelled, attach_snapshot). The adapter must resolve
credentials from the approved secret store and use the persisted snapshot
repository; credentials must never be put in the queue payload.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import socket

from app.db.session import AsyncSessionLocal
from app.services.connectors.totvs_rm_sync_orchestrator import (
    RMPostgresSyncQueue, RMSyncWorker,
)


def load_executor():
    module_name = os.environ.get("RM_SYNC_EXECUTOR_MODULE")
    if not module_name:
        raise RuntimeError(
            "RM_SYNC_EXECUTOR_MODULE não configurado. "
            "O worker não iniciará sem adapter RM homologado."
        )
    module = importlib.import_module(module_name)
    executor = getattr(module, "execute_rm_sync_job", None)
    if not callable(executor):
        raise RuntimeError("O módulo executor deve expor execute_rm_sync_job.")
    return executor


async def main(*, once: bool = False, poll_seconds: float = 2.0) -> None:
    tenant_ids = tuple(value.strip() for value in os.environ.get("RM_SYNC_WORKER_TENANT_IDS", "").split(",") if value.strip())
    if not tenant_ids:
        raise RuntimeError("RM_SYNC_WORKER_TENANT_IDS deve listar os tenants autorizados para este worker.")
    worker = RMSyncWorker(
        RMPostgresSyncQueue(AsyncSessionLocal),
        load_executor(),
        worker_id=f"{socket.gethostname()}:{os.getpid()}",
        tenant_ids=tenant_ids,
    )
    await worker.serve(once=once, poll_seconds=poll_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Worker durável de sincronização TOTVS RM")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(main(once=args.once, poll_seconds=args.poll_seconds))
