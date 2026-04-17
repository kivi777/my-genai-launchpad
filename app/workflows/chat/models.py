import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base


class Chat(Base):
    __tablename__ = "chats"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid1,
        server_default=text("gen_random_uuid()"),
    )
    message_history = Column(JSON)
    pydantic_message_history = Column(JSON)
    created_at = Column(
        DateTime,
        default=datetime.now,
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=text("now()"),
    )
