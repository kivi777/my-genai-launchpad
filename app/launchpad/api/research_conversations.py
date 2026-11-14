from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import delete, select

from launchpad.database.event import Event
from launchpad.database.research_conversation import ResearchConversation
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples.research_workspace.jobs import (
    ResearchJob,
    job_from_event,
)
from launchpad.workflows.examples.research_workspace.schema import LibraryName

router = APIRouter()


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    library: LibraryName
    title: str
    updated_at: datetime


class ConversationTurn(BaseModel):
    query: str
    job: ResearchJob


class ConversationDetail(ConversationSummary):
    turns: list[ConversationTurn]


class ConversationRename(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]


@router.get("/conversations")
def list_conversations() -> list[ConversationSummary]:
    with SessionLocal() as session:
        conversations = session.scalars(
            select(ResearchConversation)
            .where(
                select(Event.id)
                .where(Event.research_conversation_id == ResearchConversation.id)
                .exists()
            )
            .order_by(ResearchConversation.updated_at.desc(), ResearchConversation.id)
        )
        return [ConversationSummary.model_validate(row) for row in conversations]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID) -> ConversationDetail:
    with SessionLocal() as session:
        conversation = session.get(ResearchConversation, conversation_id)
        if conversation is None:
            raise HTTPException(404, "会话不存在。")
        summary = ConversationSummary.model_validate(conversation)
        events = session.scalars(
            select(Event)
            .where(Event.research_conversation_id == conversation_id)
            .order_by(Event.created_at, Event.id)
        )
        turns = [
            ConversationTurn(query=event.data["query"], job=job_from_event(event))
            for event in events
        ]
    return ConversationDetail(**summary.model_dump(), turns=turns)


@router.put("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: UUID, request: ConversationRename
) -> ConversationSummary:
    with SessionLocal.begin() as session:
        conversation = session.get(
            ResearchConversation, conversation_id, with_for_update=True
        )
        if conversation is None:
            raise HTTPException(404, "会话不存在。")
        conversation.title = request.title
        conversation.updated_at = datetime.now(UTC)
        return ConversationSummary.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID) -> Response:
    with SessionLocal.begin() as session:
        conversation = session.get(
            ResearchConversation, conversation_id, with_for_update=True
        )
        if conversation is not None:
            scope = Event.research_conversation_id == conversation_id
            events = session.scalars(select(Event).where(scope).with_for_update())
            if any(
                job_from_event(event).status in {"queued", "running"}
                for event in events
            ):
                raise HTTPException(409, "该会话还有任务在运行，请等任务结束后删除。")
            session.execute(delete(Event).where(scope))
            session.delete(conversation)
    return Response(status_code=204)
