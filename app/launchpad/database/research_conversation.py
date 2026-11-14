from sqlalchemy import Column, DateTime, String, Uuid, func

from launchpad.database.session import Base


class ResearchConversation(Base):
    __tablename__ = "research_conversations"

    id = Column(Uuid, primary_key=True)
    library = Column(String(64), nullable=False)
    title = Column(String(120), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
