from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from launchpad.database.event import Event
from launchpad.database.research_conversation import ResearchConversation
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples.research_workspace.schema import (
    ConversationMessage,
    WeeklyReportEvent,
)

ZONE = ZoneInfo("Asia/Shanghai")


def weekly_conversation_messages(event: WeeklyReportEvent) -> list[ConversationMessage]:
    # Existing event timestamps are naive application-local datetimes.
    start = (
        datetime.combine(event.week_start, time.min, ZONE)
        .astimezone()
        .replace(tzinfo=None)
    )
    end = (
        datetime.combine(event.week_end + timedelta(days=1), time.min, ZONE)
        .astimezone()
        .replace(tzinfo=None)
    )
    query = (
        select(Event, ResearchConversation.title)
        .join(
            ResearchConversation,
            Event.research_conversation_id == ResearchConversation.id,
        )
        .where(
            Event.created_at >= start,
            Event.created_at < end,
            Event.workflow_type.in_(["RESEARCH_READING", "RESEARCH_SEARCH"]),
        )
        .order_by(Event.created_at, Event.id)
    )
    if event.conversation_scope == "library":
        query = query.where(ResearchConversation.library == event.library)
    messages = []
    with SessionLocal() as session:
        for row, title in session.execute(query):
            question = (row.data.get("query") or "").strip()
            source = {
                "timestamp": row.created_at.astimezone(ZONE),
                "conversation_id": row.research_conversation_id,
                "conversation_title": title,
            }
            if question:
                messages.append(
                    ConversationMessage(
                        id=f"{row.id}:user", role="user", text=question[:6000], **source
                    )
                )
            answer = (
                (row.task_context or {})
                .get("nodes", {})
                .get("WriteReadingNoteNode", {})
                .get("note", {})
                .get("answer", "")
            ).strip()
            if answer:
                messages.append(
                    ConversationMessage(
                        id=f"{row.id}:assistant",
                        role="assistant",
                        text=answer[:6000],
                        **source,
                    )
                )
    return messages
