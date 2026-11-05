"""Membership resolution helpers — Phase B dual-read.

Prefer Membership when present; fall back to legacy User.tenant_id + User.role
so existing sessions and API keys continue to work during the transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.organization import Membership
from app.models.tenant import Tenant


@dataclass(frozen=True)
class ActiveMembership:
    user_id: str
    tenant_id: str
    role: str
    custom_role_id: Optional[str]
    membership_id: Optional[str]
    status: str
    source: str  # "membership" | "legacy_user"


def list_active_memberships(db: Session, user_id: str) -> list[Membership]:
    stmt = (
        select(Membership)
        .where(Membership.user_id == user_id, Membership.status == "active")
        .order_by(Membership.joined_at.desc().nullslast(), Membership.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def resolve_active_membership(
    db: Session,
    *,
    user: User,
    preferred_tenant_id: Optional[str] = None,
) -> Optional[ActiveMembership]:
    """Return the membership that should drive the current request context.

    Order of preference:
    1. Explicit preferred_tenant_id with an active membership
    2. Any active membership (most recent)
    3. Legacy User.tenant_id fallback
    """
    memberships = list_active_memberships(db, user.id)

    if preferred_tenant_id:
        for m in memberships:
            if m.tenant_id == preferred_tenant_id:
                return ActiveMembership(
                    user_id=user.id,
                    tenant_id=m.tenant_id,
                    role=m.role,
                    custom_role_id=m.custom_role_id,
                    membership_id=m.id,
                    status=m.status,
                    source="membership",
                )

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

    # Legacy fallback — single tenant on the user row
    if user.tenant_id:
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


def ensure_membership_for_legacy_user(db: Session, user: User) -> Membership:
    """Idempotent dual-write helper: create membership if missing."""
    existing = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.tenant_id == user.tenant_id,
        )
    )
    if existing:
        return existing

    m = Membership(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role or "coordinator",
        custom_role_id=user.custom_role_id,
        status="active" if user.is_active else "suspended",
        origin="legacy_backfill",
        joined_at=user.onboarding_completed_at or user.created_at,
    )
    db.add(m)
    db.flush()
    return m


def get_tenant_for_membership(db: Session, membership: ActiveMembership) -> Optional[Tenant]:
    return db.get(Tenant, membership.tenant_id)
