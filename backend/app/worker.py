"""Worker das filas de retenção e integrações.

Execute com: ``PYTHONPATH=. python -m app.worker`` a partir de ``backend``.
"""
from __future__ import annotations

import argparse
import asyncio
import time

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.engagement import sweep_unanswered_reads
from app.services.retention_queue import (
    process_retention_job,
    promote_due_retries,
    redis_client,
)
from app.services.jacad_queue import (
    process_jacad_sync_job,
    promote_due_jacad_retries,
    requeue_stale_jacad_jobs,
)
from app.services.sponte_queue import (
    process_sponte_sync_job,
    promote_due_sponte_retries,
    requeue_stale_sponte_jobs,
)


async def run_worker(*, once: bool = False, poll_seconds: int = 2) -> None:
    settings = get_settings()
    redis = redis_client()
    print(f"Worker Redis ouvindo {settings.retention_queue_name}, {settings.jacad_queue_name} e {settings.sponte_queue_name}")
    queue_cycle = 0
    last_engagement_sweep = 0.0
    last_jacad_recovery_sweep = 0.0
    try:
        while True:
            await promote_due_retries(redis)
            await promote_due_jacad_retries(redis)
            await promote_due_sponte_retries(redis)
            now_monotonic = time.monotonic()
            if now_monotonic - last_jacad_recovery_sweep >= 30:
                await requeue_stale_jacad_jobs(redis)
                await requeue_stale_sponte_jobs(redis)
                last_jacad_recovery_sweep = now_monotonic
            if now_monotonic - last_engagement_sweep >= settings.engagement_sweep_interval_seconds:
                try:
                    async with AsyncSessionLocal() as session:
                        summary = await sweep_unanswered_reads(session, dry_run=False)
                    print(
                        "Engagement sweep: "
                        f"{summary.get('events_created', 0)} no_response; "
                        f"{summary.get('students_updated', 0)} scores recalculados."
                    )
                except Exception as exc:
                    # Keep processing the message queue if the periodic refresh fails.
                    print(f"Aviso: engagement sweep falhou ({type(exc).__name__}).")
                last_engagement_sweep = now_monotonic
            queues = [settings.sponte_queue_name, settings.jacad_queue_name, settings.retention_queue_name]
            queue_order = queues[queue_cycle:] + queues[:queue_cycle]
            item = await redis.blpop(queue_order, timeout=poll_seconds)
            queue_cycle = (queue_cycle + 1) % len(queues)
            if item:
                queue_name, job_id = item
                if queue_name == settings.sponte_queue_name:
                    await process_sponte_sync_job(job_id, redis)
                elif queue_name == settings.jacad_queue_name:
                    await process_jacad_sync_job(job_id, redis)
                else:
                    await process_retention_job(job_id, redis)
            if once:
                break
    finally:
        await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker Redis da régua de retenção e integrações")
    parser.add_argument("--once", action="store_true", help="processa no máximo um job e encerra")
    parser.add_argument("--poll-seconds", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(run_worker(once=args.once, poll_seconds=max(1, args.poll_seconds)))


if __name__ == "__main__":
    main()
