from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select

from launchpad.database.research_meeting_prompt import ResearchMeetingPrompt
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples.research_workspace import config

router = APIRouter(prefix="/meeting-prompts")


class MeetingPromptInput(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]


class MeetingPrompt(MeetingPromptInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    updated_at: datetime


def require_storage() -> None:
    if config.DEMO_MODE:
        raise HTTPException(503, "当前演示模式未连接数据库，无法保存汇报提示。")


@router.get("")
def list_meeting_prompts() -> list[MeetingPrompt]:
    require_storage()
    with SessionLocal() as session:
        prompts = session.scalars(
            select(ResearchMeetingPrompt).order_by(
                ResearchMeetingPrompt.updated_at.desc(), ResearchMeetingPrompt.id
            )
        )
        return [MeetingPrompt.model_validate(prompt) for prompt in prompts]


@router.post("", status_code=201)
def save_meeting_prompt(request: MeetingPromptInput) -> MeetingPrompt:
    require_storage()
    with SessionLocal.begin() as session:
        prompt = ResearchMeetingPrompt(id=uuid4(), **request.model_dump())
        session.add(prompt)
        session.flush()
        return MeetingPrompt.model_validate(prompt)


@router.put("/{prompt_id}")
def update_meeting_prompt(
    prompt_id: UUID, request: MeetingPromptInput
) -> MeetingPrompt:
    require_storage()
    with SessionLocal.begin() as session:
        prompt = session.get(ResearchMeetingPrompt, prompt_id, with_for_update=True)
        if prompt is None:
            raise HTTPException(404, "这条汇报提示不存在。")
        prompt.title = request.title
        prompt.prompt = request.prompt
        prompt.updated_at = datetime.now(UTC)
        return MeetingPrompt.model_validate(prompt)
