"""Create the research library and its full-text index."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.types import UserDefinedType

revision = "20261113_research_papers"
down_revision = None
branch_labels = None
depends_on = None


class Vector1536(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kwargs: object) -> str:
        return "vector(1536)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "research_papers",
        sa.Column("library", sa.String(64), primary_key=True),
        sa.Column("paper_id", sa.String(200), primary_key=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("search_text", sa.Text, nullable=False),
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed(
                "to_tsvector('simple'::regconfig, search_text)", persisted=True
            ),
        ),
        sa.Column("embedding", Vector1536(), nullable=False),
    )
    op.create_index(
        "ix_research_papers_search",
        "research_papers",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("research_papers")
