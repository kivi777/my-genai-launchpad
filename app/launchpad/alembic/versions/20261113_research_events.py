"""Ensure the upstream event table exists on a fresh Launchpad database."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261113_research_events"
down_revision = "20261113_research_embed_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_type", sa.String(150), nullable=False),
        sa.Column("data", sa.JSON),
        sa.Column("task_context", sa.JSON),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        if_not_exists=True,
    )


def downgrade() -> None:
    # Existing installations may already own this table and its event history.
    pass
