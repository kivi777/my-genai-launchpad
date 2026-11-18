from sqlalchemy import Column, DateTime, String, Uuid, func

from launchpad.database.session import Base


class ResearchMeetingPrompt(Base):
    __tablename__ = "research_meeting_prompts"

    id = Column(Uuid, primary_key=True)
    title = Column(String(80), nullable=False)
    prompt = Column(String(1000), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
