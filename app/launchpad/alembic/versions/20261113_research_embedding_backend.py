"""Track the backend that generated each research chunk vector."""

import sqlalchemy as sa
from alembic import op

revision = "20261113_research_embed_backend"
down_revision = "20261113_research_bge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_chunks", sa.Column("embedding_backend", sa.String(100)))
    op.execute("""
        UPDATE research_chunks SET embedding_backend = 'ollama:bge-m3'
        WHERE bge_embedding IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE research_chunks SET bge_embedding = NULL
        WHERE embedding_backend = 'siliconflow:BAAI/bge-m3'
    """)
    op.drop_column("research_chunks", "embedding_backend")
