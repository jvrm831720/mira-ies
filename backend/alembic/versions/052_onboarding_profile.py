"""Persist institution profile collected during self-service onboarding."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "052_onboarding_profile"
down_revision: Union[str, None] = "051_organization_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mira_organizations",
        sa.Column("onboarding_profile", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mira_organizations", "onboarding_profile")
