"""Persist research job progress independently of the Celery result backend."""

import sqlalchemy as sa
from alembic import op

revision = "20261114_research_trace"
down_revision = "20261113_research_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("research_progress", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "research_progress")
