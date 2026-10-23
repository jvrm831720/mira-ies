"""Preview/apply job for interaction read-without-response events and dynamic risk refresh.

From backend:
  PYTHONPATH=. python scripts/refresh_engagement.py
  PYTHONPATH=. python scripts/refresh_engagement.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.services.engagement import sweep_unanswered_reads


async def _run(apply: bool) -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        return await sweep_unanswered_reads(session, dry_run=not apply)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detecta mensagens lidas sem resposta após a janela de observação."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persiste eventos no_response e recalcula score de engajamento/risco. Sem esta opção, só mostra a prévia.",
    )
    args = parser.parse_args()
    result = asyncio.run(_run(args.apply))
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
