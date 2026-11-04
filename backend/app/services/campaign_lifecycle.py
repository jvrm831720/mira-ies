"""Pure state-machine rules for the retention campaign lifecycle.

This module defines allowed transitions only. It does not schedule, enqueue,
or execute campaigns.
"""
from __future__ import annotations

from collections.abc import Iterable


CAMPAIGN_STATUSES = frozenset({
    "draft",
    "in_review",
    "changes_requested",
    "approved",
    "scheduled",
    "running",
    "paused",
    "completed",
    "cancelled",
    "failed",
})

_ALLOWED_TRANSITIONS = {
    "draft": frozenset({"in_review"}),
    "in_review": frozenset({"changes_requested", "approved"}),
    "changes_requested": frozenset({"draft"}),
    "approved": frozenset({"scheduled", "cancelled"}),
    "scheduled": frozenset({"approved", "running", "cancelled"}),
    "running": frozenset({"paused", "completed", "cancelled", "failed"}),
    "paused": frozenset({"running", "cancelled", "failed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "failed": frozenset(),
}


class CampaignTransitionError(ValueError):
    """Raised when a campaign state transition is not allowed."""


def allowed_campaign_transitions(status: str) -> frozenset[str]:
    """Return the allowed next states for a known campaign status."""
    if status not in CAMPAIGN_STATUSES:
        raise CampaignTransitionError(f"Estado de campanha desconhecido: {status}")
    return _ALLOWED_TRANSITIONS[status]


def validate_campaign_transition(current: str, target: str) -> None:
    """Raise when target is not a legal next state from current."""
    allowed = allowed_campaign_transitions(current)
    if target not in CAMPAIGN_STATUSES:
        raise CampaignTransitionError(f"Estado de destino desconhecido: {target}")
    if target not in allowed:
        raise CampaignTransitionError(
            f"Transição de campanha não permitida: {current} -> {target}"
        )


def can_transition_campaign(current: str, target: str) -> bool:
    """Boolean convenience wrapper for transition checks."""
    try:
        validate_campaign_transition(current, target)
    except CampaignTransitionError:
        return False
    return True


def validate_campaign_statuses(statuses: Iterable[str]) -> None:
    """Validate a collection of persisted statuses against the state machine."""
    unknown = sorted(set(statuses) - CAMPAIGN_STATUSES)
    if unknown:
        raise CampaignTransitionError(
            "Estados de campanha desconhecidos: " + ", ".join(unknown)
        )
