from contextlib import contextmanager
from typing import Any

from core.nodes.base import Node
from core.task import TaskContext
from workflows.chat.models import Chat
from database.repository import GenericRepository
from database.session import db_session
from workflows.chat.schema import ChatCompletionEventSchema


class PrepareChatNode(Node):
    class OutputType(Node.OutputType):
        pydantic_message_history: Any = None

    async def process(self, task_context: TaskContext) -> TaskContext:
        with contextmanager(db_session)() as session:
            event: ChatCompletionEventSchema = task_context.event

            repository = GenericRepository(session=session, model=Chat)
            chat = repository.get(id=event.id)

            output = self.OutputType(
                pydantic_message_history=chat.pydantic_message_history
            )

            self.save_output(output)

            return task_context
