"""Read-only production readiness audit for the tenant-scoped dispatch service.

Usage:
  PYTHONPATH=. python -m app.dispatch_readiness
  PYTHONPATH=. python -m app.dispatch_readiness --require-live

Never starts a worker, performs a migration or calls a message provider.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.dispatch_core import bind_tenant

TABLES=(
    "dispatch_campaigns", "dispatch_approved_templates",
    "dispatch_authorizations", "dispatch_provider_accounts",
    "dispatch_items", "dispatch_events", "dispatch_obligations",
    "dispatch_external_contacts", "dispatch_rate_buckets",
    "dispatch_inbound", "dispatch_payment_events",
    "dispatch_suppressions", "dispatch_worker_heartbeats",
)


def config_errors(settings, *, require_live: bool) -> list[str]:
    errors: list[str]=[]
    if settings.dispatch_live_enabled and settings.dispatch_dry_run_default:
        errors.append("dispatch_live_enabled requires DISPATCH_DRY_RUN_DEFAULT=false")
    if settings.dispatch_live_enabled and not settings.dispatch_worker_enabled:
        errors.append("Live sending requires the independent dispatch worker to be enabled")
    if require_live and (not settings.dispatch_live_enabled or settings.dispatch_dry_run_default):
        errors.append("Live release requested but delivery is disabled")
    channels={x.strip() for x in settings.dispatch_live_channels.split(",") if x.strip()}
    if not channels.issubset({"email","sms"}):
        errors.append("Live channels may include only email/sms; WhatsApp is simulation-only")
    tenants={x.strip() for x in settings.dispatch_live_tenants.split(",") if x.strip()}
    for tenant in tenants:
        try: UUID(tenant)
        except ValueError: errors.append("Invalid UUID in DISPATCH_LIVE_TENANTS")
    if require_live or settings.dispatch_live_enabled:
        if not tenants or not channels:
            errors.append("Explicit tenant/channel live allowlists must not be empty")
        if not settings.dispatch_provider_encryption_key:
            errors.append("Per-tenant provider encryption key is missing")
        if not settings.dispatch_trusted_authorization_sources:
            errors.append("At least one reviewed contact evidence source is required")
        if "sms" in channels:
            base=settings.dispatch_twilio_callback_base_url or ""
            if not base.startswith("https://") or not base.endswith("/api/v1/dispatch/native/twilio"):
                errors.append("Native Twilio StatusCallback HTTPS base URL is invalid")
    return errors


async def inspect(*, require_live: bool=False) -> dict:
    settings=get_settings()
    errors=config_errors(settings,require_live=require_live)
    warnings: list[str]=[]
    checked: dict[str,object]={}
    try:
        async with AsyncSessionLocal() as db:
            version=(await db.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            checked["alembic_revisions"]=[str(x) for x in version]
            if "055_dispatch_platform" not in version:
                errors.append("Migration 055_dispatch_platform not present in alembic_version")
            role=(await db.execute(text("""
                SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user
            """))).one()
            checked["non_bypass_role"]=not bool(role.rolsuper or role.rolbypassrls)
            if not checked["non_bypass_role"]:
                errors.append("Database connection uses SUPERUSER or BYPASSRLS")
            relations=(await db.execute(text("""
                SELECT relname,relrowsecurity,relforcerowsecurity
                FROM pg_class WHERE relkind='r'
                  AND relname LIKE 'dispatch_%'
            """))).mappings().all()
            rels={r["relname"]:(r["relrowsecurity"],r["relforcerowsecurity"]) for r in relations}
            missing=[table for table in TABLES if table not in rels]
            unchecked=[table for table in TABLES if table in rels
                       and not all(rels[table])]
            checked["table_count"]=len(rels)
            checked["expected_table_count"]=len(TABLES)
            if missing: errors.append("Missing dispatch tables: "+", ".join(missing))
            if unchecked: errors.append("Tables missing FORCE RLS: "+", ".join(unchecked))
            triggers=(await db.execute(text("""
                SELECT tgname FROM pg_trigger WHERE NOT tgisinternal
                  AND tgname IN ('dispatch_events_immutable','dispatch_payments_immutable')
            """))).scalars().all()
            if len(triggers)<2:
                errors.append("Append-only ledger/audit triggers are missing")
            if settings.dispatch_live_enabled:
                allowed={x.strip() for x in settings.dispatch_live_tenants.split(",") if x.strip()}
                channels={x.strip() for x in settings.dispatch_live_channels.split(",") if x.strip()}
                for tenant_id in sorted(allowed):
                    try: UUID(tenant_id)
                    except ValueError: continue
                    # Each query has a verified transaction-local RLS tenant binding.
                    await bind_tenant(db,tenant_id)
                    available=(await db.execute(text("""
                        SELECT provider,status,last_verified_at FROM dispatch_provider_accounts
                        WHERE tenant_id=:tenant
                    """), {"tenant":tenant_id})).mappings().all()
                    provider_map={row["provider"]:row for row in available}
                    from datetime import datetime,timedelta,timezone
                    for channel in channels:
                        provider="resend" if channel=="email" else "twilio"
                        entry=provider_map.get(provider)
                        if (entry is None or entry["status"]!="active"
                              or entry["last_verified_at"] is None
                              or entry["last_verified_at"]<datetime.now(timezone.utc)-timedelta(days=30)):
                            errors.append(f"Tenant {tenant_id}: {provider} not recently verified and active")
                    last=(await db.execute(text("""
                        SELECT max(seen_at) FROM dispatch_worker_heartbeats
                        WHERE tenant_id=:tenant
                    """), {"tenant":tenant_id})).scalar_one()
                    if not last or last<datetime.now(timezone.utc)-timedelta(seconds=90):
                        warnings.append(f"Tenant {tenant_id}: no worker heartbeat in last 90s")
    except Exception as exc:
        errors.append("Database readiness query failed: "+type(exc).__name__)
    return {
        "ready":not errors and (not require_live or not warnings),
        "live_requested":require_live,
        "live_enabled":settings.dispatch_live_enabled,
        "dry_run_default":settings.dispatch_dry_run_default,
        "checks":checked,"errors":errors,"warnings":warnings,
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="MIRA dispatch readiness (read only)")
    parser.add_argument("--require-live",action="store_true")
    args=parser.parse_args()
    report=asyncio.run(inspect(require_live=args.require_live))
    print(json.dumps(report,ensure_ascii=False,indent=2,default=str))
    if not report["ready"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
