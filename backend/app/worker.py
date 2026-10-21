"""Worker da fila de retenção.

Execute com: ``PYTHONPATH=. python -m app.worker`` a partir de ``backend``.
"""
from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.services.retention_queue import (
    process_retention_job,
    promote_due_retries,
    redis_client,
)


async def run_worker(*, once: bool = False, poll_seconds: int = 2) -> None:
    settings = get_settings()
    redis = redis_client()
    print(f"Retention worker ouvindo {settings.retention_queue_name}")
    try:
        while True:
            await promote_due_retries(redis)
            item = await redis.blpop(settings.retention_queue_name, timeout=poll_seconds)
            if item:
                await process_retention_job(item[1], redis)
            if once:
                break
    finally:
        await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker Redis da régua de retenção")
    parser.add_argument("--once", action="store_true", help="processa no máximo um job e encerra")
    parser.add_argument("--poll-seconds", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(run_worker(once=args.once, poll_seconds=max(1, args.poll_seconds)))


if __name__ == "__main__":
    main()
