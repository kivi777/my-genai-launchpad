from sqlalchemy import (
    Column,
    Computed,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.types import UserDefinedType

from launchpad.database.session import Base
from launchpad.workflows.examples.research_workspace.config import EMBEDDING_DIMENSIONS


class ResearchVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kwargs: object) -> str:
        return f"vector({self.dimensions})"


class ResearchPaper(Base):
    __tablename__ = "research_papers"
    __table_args__ = (
        Index("ix_research_papers_search", "search_vector", postgresql_using="gin"),
    )

    library = Column(String(64), primary_key=True)
    paper_id = Column(String(200), primary_key=True)
    payload = Column(JSONB, nullable=False)
    search_text = Column(Text, nullable=False)
    search_vector = Column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, search_text)", persisted=True),
    )
    embedding = Column(ResearchVector(1536))


class ResearchChunk(Base):
    __tablename__ = "research_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library", "paper_id"],
            ["research_papers.library", "research_papers.paper_id"],
            ondelete="CASCADE",
        ),
        Index("ix_research_chunks_search", "search_vector", postgresql_using="gin"),
    )

    library = Column(String(64), primary_key=True)
    paper_id = Column(String(200), primary_key=True)
    number = Column(Integer, primary_key=True)
    chunk = Column(JSONB, nullable=False)
    search_vector = Column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, chunk ->> 'text')", persisted=True),
    )
    embedding = Column(ResearchVector(1536))
    bge_embedding = Column(ResearchVector(EMBEDDING_DIMENSIONS))
    embedding_backend = Column(String(100))
