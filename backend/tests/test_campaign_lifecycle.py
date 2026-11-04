import pytest

from app.services.campaign_lifecycle import (
    CAMPAIGN_STATUSES,
    CampaignTransitionError,
    allowed_campaign_transitions,
    can_transition_campaign,
    validate_campaign_transition,
)


def test_campaign_lifecycle_contains_existing_and_operational_states():
    assert CAMPAIGN_STATUSES == {
        "draft", "in_review", "changes_requested", "approved", "scheduled",
        "running", "paused", "completed", "cancelled", "failed",
    }


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "in_review"),
        ("in_review", "changes_requested"),
        ("in_review", "approved"),
        ("changes_requested", "draft"),
        ("approved", "scheduled"),
        ("approved", "cancelled"),
        ("scheduled", "approved"),
        ("scheduled", "running"),
        ("scheduled", "cancelled"),
        ("running", "paused"),
        ("running", "completed"),
        ("running", "cancelled"),
        ("running", "failed"),
        ("paused", "running"),
        ("paused", "cancelled"),
        ("paused", "failed"),
    ],
)
def test_allowed_campaign_transitions(current, target):
    validate_campaign_transition(current, target)
    assert can_transition_campaign(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "approved"),
        ("approved", "running"),
        ("completed", "running"),
        ("cancelled", "scheduled"),
        ("failed", "running"),
        ("paused", "completed"),
        ("unknown", "draft"),
        ("draft", "unknown"),
    ],
)
def test_rejects_invalid_campaign_transitions(current, target):
    with pytest.raises(CampaignTransitionError):
        validate_campaign_transition(current, target)
    assert not can_transition_campaign(current, target)


def test_terminal_states_have_no_outgoing_transitions():
    for status in ("completed", "cancelled", "failed"):
        assert allowed_campaign_transitions(status) == frozenset()


def test_unknown_status_is_rejected_when_listing_transitions():
    with pytest.raises(CampaignTransitionError, match="desconhecido"):
        allowed_campaign_transitions("queued")
