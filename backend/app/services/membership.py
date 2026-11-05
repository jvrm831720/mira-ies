"""Membership resolution — Phase B dual-read / dual-write (async).

Prefer Membership when present; fall back to legacy User.tenant_id + User.role
so existing sessions continue to work during the transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.organization import Membership
from app.models.tenant import Tenant


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ActiveMembership:
    user_id: str
    tenant_id: str
    role: str
    custom_role_id: Optional[str]
    membership_id: Optional[str]
    status: str
    source: str  # "membership" | "legacy_user"


async def list_active_memberships(db: AsyncSession, user_id: str) -> list[Membership]:
    result = await db.execute(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.status == "active")
        .order_by(Membership.joined_at.desc().nullslast(), Membership.created_at.desc())
    )
    return list(result.scalars().all())


async def get_membership_for_tenant(
    db: AsyncSession,
    *,
    user_id: str,
    tenant_id: str,
    for_update: bool = False,
) -> Optional[Membership]:
    query = select(Membership).where(
        Membership.user_id == user_id,
        Membership.tenant_id == tenant_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def resolve_active_membership(
    db: AsyncSession,
    *,
    user: User,
    preferred_tenant_id: Optional[str] = None,
) -> Optional[ActiveMembership]:
    """Membership that should drive the current request context."""
    # An existing but inactive membership is an explicit denial, not a reason
    # to fall back to the legacy User.tenant_id identity.
    if preferred_tenant_id:
        preferred = await get_membership_for_tenant(
            db, user_id=user.id, tenant_id=preferred_tenant_id
        )
        if preferred:
            return ActiveMembership(
                user_id=user.id,
                tenant_id=preferred.tenant_id,
                role=preferred.role,
                custom_role_id=preferred.custom_role_id,
                membership_id=preferred.id,
                status=preferred.status,
                source="membership",
            )

    memberships = await list_active_memberships(db, user.id)

    if memberships:
        m = memberships[0]
        return ActiveMembership(
            user_id=user.id,
            tenant_id=m.tenant_id,
            role=m.role,
            custom_role_id=m.custom_role_id,
            membership_id=m.id,
            status=m.status,
            source="membership",
        )

    if user.tenant_id:
        legacy_membership = await get_membership_for_tenant(
            db, user_id=user.id, tenant_id=user.tenant_id
        )
        if legacy_membership:
            return ActiveMembership(
                user_id=user.id,
                tenant_id=legacy_membership.tenant_id,
                role=legacy_membership.role,
                custom_role_id=legacy_membership.custom_role_id,
                membership_id=legacy_membership.id,
                status=legacy_membership.status,
                source="membership",
            )
        return ActiveMembership(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role or "coordinator",
            custom_role_id=user.custom_role_id,
            membership_id=None,
            status="active" if user.is_active else "suspended",
            source="legacy_user",
        )

    return None


async def ensure_membership(
    db: AsyncSession,
    *,
    user: User,
    tenant_id: Optional[str] = None,
    role: Optional[str] = None,
    custom_role_id: Optional[str] = None,
    origin: str = "legacy_backfill",
    status: str = "active",
) -> Membership:
    """Create a missing legacy membership without mutating an existing grant.

    Status and role transitions must be performed by authorized, tenant-scoped
    workflows; login/session creation is never such a workflow.
    """
    tid = tenant_id or user.tenant_id
    if not tid:
        raise ValueError("tenant_id is required to ensure membership")

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.tenant_id == tid,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    m = Membership(
        id=str(uuid4()),
        user_id=user.id,
        tenant_id=tid,
        role=role or user.role or "coordinator",
        custom_role_id=custom_role_id if custom_role_id is not None else user.custom_role_id,
        status=status,
        origin=origin,
        joined_at=user.onboarding_completed_at or user.created_at or _now(),
    )
    db.add(m)
    await db.flush()
    return m


async def sync_membership_role(
    db: AsyncSession,
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    custom_role_id: Optional[str] = None,
) -> Optional[Membership]:
    """Update membership role when User.role is changed (dual-write)."""
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        return None
    m.role = role
    m.custom_role_id = custom_role_id
    return m


async def get_tenant_for_membership(db: AsyncSession, membership: ActiveMembership) -> Optional[Tenant]:
    return await db.get(Tenant, membership.tenant_id)
