"""Store PDF annotations and page notes in separate tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261113_research_reader"
down_revision = "20261113_research_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_pdf_annotations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pdf_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("regions", JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_research_pdf_annotations_pdf", "research_pdf_annotations", ["pdf_id"]
    )
    op.create_table(
        "research_pdf_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pdf_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_research_pdf_notes_pdf", "research_pdf_notes", ["pdf_id"])


def downgrade() -> None:
    op.drop_table("research_pdf_notes")
    op.drop_table("research_pdf_annotations")
