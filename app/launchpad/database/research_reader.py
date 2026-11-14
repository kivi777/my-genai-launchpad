from sqlalchemy import Column, DateTime, Index, Integer, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB

from launchpad.database.session import Base


class ResearchAnnotation(Base):
    __tablename__ = "research_pdf_annotations"
    __table_args__ = (Index("ix_research_pdf_annotations_pdf", "pdf_id"),)

    id = Column(Uuid, primary_key=True)
    pdf_id = Column(Uuid, nullable=False)
    page = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    quote = Column(Text, nullable=False)
    regions = Column(JSONB, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchReaderNote(Base):
    __tablename__ = "research_pdf_notes"
    __table_args__ = (Index("ix_research_pdf_notes_pdf", "pdf_id"),)

    id = Column(Uuid, primary_key=True)
    pdf_id = Column(Uuid, nullable=False)
    page = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
