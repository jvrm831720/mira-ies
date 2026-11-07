#!/usr/bin/env python3
"""Read-only Wave 7 database drift and migration preflight.

Reads only schema/extension/index metadata, no tenant data and no secrets.
Never applies a migration, creates indexes or modifies a service.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

REQUIRED_REVISION = "072_federated_search"
REQUIRED_INDEXES = frozenset({
    "ix_search_students_name_trgm",
    "ix_search_students_enrollment_trgm",
    "ix_search_finance_external_ref_trgm",
    "ix_search_finance_subject_ref_trgm",
    "ix_search_work_title_trgm",
    "ix_search_view_name_trgm",
    "ix_search_proposal_title_trgm",
})
FORCE_RLS_TABLES = frozenset({
    "mira_object_views", "mira_object_view_revisions",
    "mira_object_view_favorites",
})


def assess(metadata: dict) -> dict:
    violations = []
    if metadata.get("revision") != REQUIRED_REVISION:
        violations.append("schema_revision_drift")
    if not metadata.get("pg_trgm"):
        violations.append("pg_trgm_not_installed")
    if metadata.get("is_superuser") or metadata.get("bypass_rls"):
        violations.append("unsafe_database_runtime_role")
    indexes = set(metadata.get("indexes") or [])
    for name in sorted(REQUIRED_INDEXES - indexes):
        violations.append("missing_index:" + name)
    for table in sorted(FORCE_RLS_TABLES):
        flags = (metadata.get("rls") or {}).get(table) or {}
        if flags.get("rls") is not True or flags.get("force") is not True:
            violations.append("missing_forced_rls:" + table)
    # Never infer that production's migration can safely build an index
    # based solely on metadata; existing relation sizes require review.
    size_bytes = metadata.get("relation_bytes") or {}
    largest = max(size_bytes.values(), default=0)
    warnings = []
    if largest >= 1024**3:
        warnings.append("large_relation_index_build_requires_maintenance_approval")
    return {
        "decision": "PASS" if not violations else "BLOCK",
        "revision_expected": REQUIRED_REVISION,
        "violations": violations, "warnings": warnings,
        "max_relation_bytes": largest,
        "read_only": True,
    }


async def inspect(dsn: str) -> dict:
    import asyncpg

    conn = await asyncpg.connect(dsn, timeout=10, command_timeout=10)
    try:
        revision = await conn.fetchval(
            "SELECT version_num FROM alembic_version LIMIT 1"
        )
        role = await conn.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        extension = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_trgm')"
        )
        rows = await conn.fetch("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
              AND c.relname = ANY($1::text[])
        """, list(FORCE_RLS_TABLES))
        indexes = await conn.fetch("""
            SELECT indexname FROM pg_indexes
            WHERE schemaname='public' AND indexname=ANY($1::text[])
        """, list(REQUIRED_INDEXES))
        sizes = await conn.fetch("""
            SELECT c.relname, pg_total_relation_size(c.oid) AS bytes
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
              AND c.relname=ANY($1::text[])
        """, [
            "students", "dispatch_obligations", "work_activities",
            "mira_object_views", "retention_campaign_proposals",
        ])
        return {
            "revision": revision,
            "pg_trgm": extension,
            "is_superuser": bool(role["rolsuper"]) if role else True,
            "bypass_rls": bool(role["rolbypassrls"]) if role else True,
            "rls": {row["relname"]: {
                "rls": row["relrowsecurity"], "force": row["relforcerowsecurity"]
            } for row in rows},
            "indexes": [row["indexname"] for row in indexes],
            "relation_bytes": {row["relname"]: row["bytes"] for row in sizes},
        }
    finally:
        await conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    dsn = (os.getenv("DATABASE_URL_SYNC") or "").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    if not dsn.startswith("postgresql://"):
        print("Read-only preflight requires DATABASE_URL_SYNC.", file=sys.stderr)
        return 2
    try:
        verdict = assess(asyncio.run(inspect(dsn)))
    except Exception as exc:
        # Never log DB URLs or engine messages (may include credentials).
        print("Database metadata inspection failed: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(verdict, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("Wave 7 schema preflight:", verdict["decision"],
          "violations:", len(verdict["violations"]),
          "warnings:", len(verdict["warnings"]))
    return 0 if verdict["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
