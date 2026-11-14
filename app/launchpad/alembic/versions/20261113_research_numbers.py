"""Allocate stable import numbers per research library."""

import sqlalchemy as sa
from alembic import op

revision = "20261113_research_numbers"
down_revision = "20261113_research_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_library_counters",
        sa.Column("library", sa.String(64), primary_key=True),
        sa.Column("last_id", sa.Numeric(201, 0), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("research_library_counters")
