"""Fail-closed disclosure for student-visible service events.

Status transitions can contain institutional notes with no public/private flag.
The student portal must not serialize staff/system notes as student-visible content.
"""
from __future__ import annotations


def student_visible_event_note(actor_type: str, note: str | None) -> str | None:
    if actor_type == "student":
        return note
    return None
