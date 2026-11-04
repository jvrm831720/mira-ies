import pytest

from app.services.campaign_proposals import deduplicate_audience_members, hash_audience_snapshot


def test_audience_snapshot_deduplicates_students_and_merges_groups_and_channels():
    snapshot = deduplicate_audience_members([
        {
            "student_id": "student-b",
            "matricula": "B",
            "matched_group_ids": ["risk_critical"],
            "eligible_channels": ["whatsapp"],
            "blocked_reasons": [],
            "internal_action_only": False,
        },
        {
            "student_id": "student-b",
            "matricula": "B",
            "matched_group_ids": ["multiple_active_signals"],
            "eligible_channels": ["email"],
            "blocked_reasons": [],
            "internal_action_only": False,
        },
        {
            "student_id": "student-a",
            "matricula": "A",
            "matched_group_ids": ["missing_score"],
            "eligible_channels": [],
            "blocked_reasons": ["internal_data_quality_action"],
            "internal_action_only": True,
        },
    ])

    assert [item["student_id"] for item in snapshot] == ["student-a", "student-b"]
    assert snapshot[1]["matched_group_ids"] == ["multiple_active_signals", "risk_critical"]
    assert snapshot[1]["eligible_channels"] == ["email", "whatsapp"]
    assert snapshot[0]["eligible_channels"] == []
    assert snapshot[0]["internal_action_only"] is True


def test_internal_only_membership_does_not_suppress_a_confirmed_outreach_group():
    snapshot = deduplicate_audience_members([
        {
            "student_id": "student-a",
            "matricula": "A",
            "matched_group_ids": ["missing_score"],
            "eligible_channels": [],
            "blocked_reasons": ["internal_data_quality_action"],
            "internal_action_only": True,
        },
        {
            "student_id": "student-a",
            "matricula": "A",
            "matched_group_ids": ["risk_critical"],
            "eligible_channels": ["email"],
            "blocked_reasons": [],
            "internal_action_only": False,
        },
    ])

    assert snapshot[0]["internal_action_only"] is False
    assert snapshot[0]["eligible_channels"] == ["email"]


def test_audience_hash_is_stable_for_canonical_snapshot():
    snapshot = [{"student_id": "s1", "eligible_channels": ["email"], "matched_group_ids": ["risk_medium"]}]
    assert hash_audience_snapshot(snapshot) == hash_audience_snapshot(snapshot)
    assert len(hash_audience_snapshot(snapshot)) == 64


def test_audience_hash_changes_when_membership_or_eligibility_changes():
    first = [{"student_id": "s1", "eligible_channels": ["email"]}]
    second = [{"student_id": "s1", "eligible_channels": []}]
    assert hash_audience_snapshot(first) != hash_audience_snapshot(second)
