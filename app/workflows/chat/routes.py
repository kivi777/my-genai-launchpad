import json
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import Response

from database.event import Event
from database.repository import GenericRepository
from database.session import db_session
from workflows.chat.schema import ChatCompletionEventSchema
from worker.config import celery_app
from workflows.chat.workflow import ChatExampleWorkflow
from workflows.chat.nodes.update_chat_node import UpdateChatNode
from workflows.workflow_registry import WorkflowRegistry

router = APIRouter()


@router.post("/direct", dependencies=[])
async def handle_chat(
    data: ChatCompletionEventSchema,
) -> Response:
    """Handles incoming chat requests directly (synchronous workflow execution).

    Args:
        data: The chat completion event data.

    Returns:
        Response with the generated chat reply.
    """
    task_context = await ChatExampleWorkflow().run_async(data.model_dump())
    update_chat_node: UpdateChatNode.OutputType = task_context.nodes.get(
        UpdateChatNode.__name__
    )

    return Response(
        content=json.dumps(update_chat_node.response_content),
        headers={"Content-Type": "application/json"},
        status_code=HTTPStatus.OK,
    )


@router.post("/websocket", dependencies=[])
async def handle_websocket_chat(
    data: ChatCompletionEventSchema,
    session: Session = Depends(db_session),
) -> Response:
    """Handles chat requests via async Celery task (for WebSocket consumers).

    Args:
        data: The chat completion event data.
        session: Database session.

    Returns:
        Response with the queued task ID.
    """
    repository = GenericRepository(
        session=session,
        model=Event,
    )
    raw_event = data.model_dump(mode="json")
    event = Event(data=raw_event, workflow_type=WorkflowRegistry.CHAT.name)
    repository.create(obj=event)

    task_id = celery_app.send_task(
        "process_incoming_event",
        args=[str(event.id)],
    )

    return Response(
        content=json.dumps({"message": f"process_incoming_event started `{task_id}` "}),
        status_code=HTTPStatus.ACCEPTED,
    )
