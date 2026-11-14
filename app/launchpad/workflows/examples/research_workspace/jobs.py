from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from sqlalchemy import func, select, update

from launchpad.database.event import Event
from launchpad.database.research_conversation import ResearchConversation
from launchpad.database.research_number import next_resource_id
from launchpad.database.session import SessionLocal
from launchpad.worker.config import celery_app
from launchpad.workflows.workflow_registry import WorkflowRegistry

from .observability import STEP_LABELS, TaskProgress, TaskStep
from .schema import (
    NotionImportEvent,
    PdfImportEvent,
    PreviousTurn,
    ResearchEvent,
    SearchEvent,
)


class ResearchJob(BaseModel):
    run_id: UUID
    conversation_id: UUID | None = None
    status: Literal["queued", "running", "completed", "failed"]
    trace_id: str | None = None
    trace_url: str | None = None
    failed_step: str | None = None
    queue_ms: int | None = None
    steps: list[TaskStep] = Field(default_factory=list)
    outputs: dict | None = None
    message: str | None = None


class DispatchError(RuntimeError):
    def __init__(self, run_id: UUID):
        super().__init__("Could not confirm that Redis received the research job.")
        self.run_id = run_id


class ConversationNotFoundError(Exception):
    pass


class ConversationLibraryError(Exception):
    pass


def submit_job(
    request: ResearchEvent,
    workflow: WorkflowRegistry,
    run_id: UUID | None = None,
    *,
    conversation_id: UUID | None = None,
    start_conversation: bool = False,
) -> ResearchJob:
    run_id = run_id or uuid4()
    # Commit before publishing so a fast worker can always load the event.
    with SessionLocal.begin() as session:
        if isinstance(request, PdfImportEvent) and request.paper.id is None:
            paper = request.paper.model_copy(
                update={"id": next_resource_id(session, request.library)}
            )
            request = request.model_copy(update={"paper": paper})
        if isinstance(request, NotionImportEvent) and request.page_id is None:
            request = request.model_copy(
                update={"resource_id": next_resource_id(session, request.library)}
            )
        if start_conversation and isinstance(request, SearchEvent):
            conversation_id = uuid4()
            session.add(
                ResearchConversation(
                    id=conversation_id,
                    library=request.library,
                    title=" ".join(request.query.split())[:120],
                )
            )
            session.flush()
        elif conversation_id is not None and isinstance(request, SearchEvent):
            conversation = session.get(
                ResearchConversation, conversation_id, with_for_update=True
            )
            if conversation is None:
                raise ConversationNotFoundError
            recent = list(
                session.execute(
                    select(Event.data, Event.task_context)
                    .where(Event.research_conversation_id == conversation_id)
                    .order_by(Event.created_at.desc(), Event.id.desc())
                    .limit(6)
                )
            )
            if not recent:
                conversation.title = " ".join(request.query.split())[:120]
                conversation.library = request.library
            elif conversation.library != request.library:
                raise ConversationLibraryError
            previous_turns = []
            for turn in reversed(recent):
                if turn.task_context is None:
                    continue
                note = (
                    turn.task_context["nodes"]
                    .get("WriteReadingNoteNode", {})
                    .get("note", {})
                )
                previous_turns.append(
                    PreviousTurn(
                        question=turn.data["query"],
                        answer=note.get("answer", "")[:1600],
                    )
                )
            request = request.model_copy(update={"previous_turns": previous_turns})
            conversation.updated_at = func.now()
        session.add(
            Event(
                id=run_id,
                workflow_type=workflow.name,
                research_conversation_id=conversation_id,
                research_progress={"status": "queued"},
                data=request.model_dump(mode="json", exclude={"action"}),
            )
        )

    try:
        celery_app.send_task(
            "process_incoming_event", args=[str(run_id)], task_id=str(run_id)
        )
    except Exception as exc:
        # Publication can fail after Redis received the message. Keep the input
        # and event so a worker that received it can still finish.
        progress = TaskProgress(
            status="failed",
            failed_step=STEP_LABELS["dispatch"],
            message="无法确认 Redis 已接收任务。",
            steps=[
                TaskStep(
                    key="dispatch",
                    label=STEP_LABELS["dispatch"],
                    depth=0,
                    status="failed",
                    started_at=datetime.now(UTC),
                    error="无法确认 Redis 已接收任务。",
                )
            ],
        )
        with SessionLocal.begin() as session:
            session.execute(
                update(Event)
                .where(
                    Event.id == run_id,
                    Event.research_progress["status"].as_string() == "queued",
                )
                .values(
                    research_progress=progress.model_dump(
                        mode="json", exclude_none=True
                    )
                )
            )
        raise DispatchError(run_id) from exc
    return ResearchJob(run_id=run_id, status="queued", conversation_id=conversation_id)


def get_job(run_id: UUID, *, library: str | None = None) -> ResearchJob | None:
    with SessionLocal() as session:
        event = session.get(Event, run_id)
        if event is None or not event.workflow_type.startswith("RESEARCH_"):
            return None
        if library is not None and event.data.get("library") != library:
            return None
        return job_from_event(event)


def recent_jobs(library: str, workflow: WorkflowRegistry) -> list[ResearchJob]:
    with SessionLocal() as session:
        events = session.scalars(
            select(Event)
            .where(
                Event.workflow_type == workflow.name,
                Event.data["library"].as_string() == library,
            )
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(15)
        )
        return [
            job_from_event(event).model_copy(update={"outputs": None})
            for event in events
        ]


def celery_state(run_id: UUID) -> str | None:
    try:
        return celery_app.AsyncResult(str(run_id)).state
    except (RedisError, OSError):
        return None


def job_from_event(event: Event) -> ResearchJob:
    run_id = event.id
    context = event.task_context
    if event.research_progress:
        progress = TaskProgress.model_validate(event.research_progress)
        if (
            context is not None
            and progress.status in {"queued", "running"}
            and (not progress.steps or progress.steps[-1].key != "save_result")
        ):
            progress.status = "completed"
        if progress.status in {"queued", "running"} and context is None:
            state = celery_state(run_id)
            if state in {"FAILURE", "REVOKED"}:
                active = next(
                    (
                        step
                        for step in reversed(progress.steps)
                        if step.status == "running"
                    ),
                    None,
                )
                if active:
                    active.status = "failed"
                    active.error = "Worker 在该步骤中断。"
                    progress.failed_step = active.label
                progress.status = "failed"
                progress.message = "Worker 执行中断，可用任务 ID 查询日志。"
        return ResearchJob(
            run_id=run_id,
            conversation_id=event.research_conversation_id,
            status=progress.status,
            steps=progress.steps,
            trace_id=progress.trace_id,
            trace_url=str(progress.trace_url) if progress.trace_url else None,
            failed_step=progress.failed_step,
            queue_ms=progress.queue_ms,
            message=progress.message,
            outputs=context["nodes"] if context else None,
        )
    if context is not None:
        return ResearchJob(
            run_id=run_id,
            conversation_id=event.research_conversation_id,
            status="completed",
            trace_id=context.get("trace_id"),
            outputs=context["nodes"],
        )
    state = celery_state(run_id)
    if state in {"FAILURE", "REVOKED"}:
        return ResearchJob(
            run_id=run_id,
            conversation_id=event.research_conversation_id,
            status="failed",
            message="Check the Celery worker logs.",
        )
    return ResearchJob(
        run_id=run_id,
        conversation_id=event.research_conversation_id,
        status="running" if state == "STARTED" else "queued",
    )
