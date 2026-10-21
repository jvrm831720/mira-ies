"""Create Mira account and one-time authentication challenge tables.

Revision ID: 003_mira_auth
Revises: 002_agents
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_mira_auth"
down_revision: Union[str, None] = "002_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create any missing application tables as well as the new auth tables. Existing tables/data
    # are left untouched because SQLAlchemy's checkfirst only creates absent tables and indexes.
    from app.db.session import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("mira_auth_challenges")
    op.drop_table("mira_users")
