"""Fail-closed schema readiness for real Render deployments.

An external process can swallow Alembic's exit code; production startup must
still refuse to serve endpoints when its code and database disagree.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.db.session as db_session


class SchemaReadinessError(RuntimeError):
    """Schema and server revision differ; no traffic may be served."""


@lru_cache(maxsize=1)
def expected_schema_revision() -> str:
    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        raise SchemaReadinessError("Alembic has multiple or missing heads.")
    return heads[0]


def validate_schema_revision(actual: str | None, expected: str) -> None:
    if not actual or actual != expected:
        raise SchemaReadinessError(
            "Database migration revision differs from the deployed application."
        )


async def assert_schema_ready() -> str:
    expected = expected_schema_revision()
    try:
        async with db_session.engine.connect() as conn:
            actual = await conn.scalar(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
    except (SQLAlchemyError, OSError) as exc:
        raise SchemaReadinessError("Database schema unavailable.") from exc
    validate_schema_revision(actual, expected)
    return expected
