"""Preview ou execução explícita do TTL dos logs brutos de intervenção.

Uso (a partir de backend):
  PYTHONPATH=. python scripts/purge_intervention_logs.py
  PYTHONPATH=. python scripts/purge_intervention_logs.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.services.intervention_log_retention import purge_expired_intervention_logs


async def _run(apply: bool) -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        return await purge_expired_intervention_logs(session, dry_run=not apply)


def main() -> None:
    parser = argparse.ArgumentParser(description="Arquiva em agregados e expurga logs de intervenção vencidos.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Confirma a gravação dos agregados e exclusão dos logs vencidos. Sem esta opção, só mostra a prévia.",
    )
    args = parser.parse_args()
    result = asyncio.run(_run(args.apply))
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
