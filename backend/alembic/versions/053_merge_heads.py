"""Merge the Phase B RLS and onboarding profile revision heads.

Revision ID: 053_merge_heads
Revises: 052_phase_b_rls, 052_onboarding_profile
Create Date: 2026-11-05
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "053_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "052_phase_b_rls",
    "052_onboarding_profile",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
