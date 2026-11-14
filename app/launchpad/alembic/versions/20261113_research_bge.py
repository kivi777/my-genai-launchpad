"""Add BGE-M3 vectors while preserving legacy chunks for keyword search."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.types import UserDefinedType

revision = "20261113_research_bge"
down_revision = "20261113_research_chunks"
branch_labels = None
depends_on = None


class Vector1024(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kwargs: object) -> str:
        return "vector(1024)"


def upgrade() -> None:
    op.add_column("research_chunks", sa.Column("bge_embedding", Vector1024()))
    op.alter_column("research_chunks", "embedding", nullable=True)
    op.alter_column("research_papers", "embedding", nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("research_chunks", "research_papers"):
        if bind.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE embedding IS NULL)")
        ).scalar():
            raise RuntimeError(
                "Downgrade requires restoring legacy 1536-dimensional vectors first"
            )
    op.alter_column("research_chunks", "embedding", nullable=False)
    op.alter_column("research_papers", "embedding", nullable=False)
    op.drop_column("research_chunks", "bge_embedding")
