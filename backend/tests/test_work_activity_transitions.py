"""Pure tests for WorkActivity status transitions (no DB)."""

ALLOWED = {
    "open": {"in_progress", "completed", "cancelled"},
    "in_progress": {"open", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED.get(current, set())


def test_open_can_start_complete_cancel():
    assert can_transition("open", "in_progress")
    assert can_transition("open", "completed")
    assert can_transition("open", "cancelled")
    assert not can_transition("open", "open")


def test_terminal_states_are_final():
    assert not can_transition("completed", "open")
    assert not can_transition("completed", "in_progress")
    assert not can_transition("cancelled", "open")
    assert not can_transition("cancelled", "completed")


def test_in_progress_can_reopen():
    assert can_transition("in_progress", "open")
    assert can_transition("in_progress", "completed")
