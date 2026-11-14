"""Associate research query events with persistent conversations."""

import sqlalchemy as sa
from alembic import op

revision = "20261113_research_conversations"
down_revision = "20261113_research_reader"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("library", sa.String(64), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column("events", sa.Column("research_conversation_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_events_research_conversation",
        "events",
        "research_conversations",
        ["research_conversation_id"],
        ["id"],
    )
    op.create_index(
        "ix_events_research_conversation_id", "events", ["research_conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_events_research_conversation_id", table_name="events")
    op.drop_constraint("fk_events_research_conversation", "events", type_="foreignkey")
    op.drop_column("events", "research_conversation_id")
    op.drop_table("research_conversations")
