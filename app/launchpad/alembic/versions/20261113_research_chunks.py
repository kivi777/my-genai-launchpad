"""Add passage-level search with a backfill for existing summary records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.types import UserDefinedType

revision = "20261113_research_chunks"
down_revision = "20261113_research_papers"
branch_labels = None
depends_on = None


class Vector1536(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kwargs: object) -> str:
        return "vector(1536)"


def upgrade() -> None:
    op.create_table(
        "research_chunks",
        sa.Column("library", sa.String(64), primary_key=True),
        sa.Column("paper_id", sa.String(200), primary_key=True),
        sa.Column("number", sa.Integer, primary_key=True),
        sa.Column("chunk", JSONB, nullable=False),
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('simple'::regconfig, chunk ->> 'text')", persisted=True
            ),
        ),
        sa.Column("embedding", Vector1536(), nullable=False),
        sa.ForeignKeyConstraint(
            ["library", "paper_id"],
            ["research_papers.library", "research_papers.paper_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_research_chunks_search",
        "research_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.execute("""
        INSERT INTO research_chunks (library, paper_id, number, chunk, embedding)
        SELECT library, paper_id, 1, jsonb_build_object('number', 1, 'text', search_text), embedding
        FROM research_papers
    """)


def downgrade() -> None:
    op.drop_table("research_chunks")
