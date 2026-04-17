from contextlib import contextmanager
from typing import Any

from core.nodes.base import Node
from core.task import TaskContext
from workflows.chat.models import Chat
from database.repository import GenericRepository
from database.session import db_session
from workflows.chat.schema import ChatCompletionEventSchema
from workflows.chat.nodes.chat_completion_node import ChatCompletionNode


class UpdateChatNode(Node):
    class OutputType(Node.OutputType):
        response_content: Any

    async def process(self, task_context: TaskContext) -> TaskContext:
        with contextmanager(db_session)() as session:
            event: ChatCompletionEventSchema = task_context.event

            repository = GenericRepository(session=session, model=Chat)
            chat = repository.get(id=event.id)

            chat_completion_node: ChatCompletionNode.OutputType = self.get_output(
                ChatCompletionNode
            )

            new_messages = [
                {
                    "role": event.role,
                    "content": event.content,
                },
                {"role": "assistant", "content": chat_completion_node.model_output},
            ]

            messages = chat.message_history
            if messages:
                chat.message_history = messages + new_messages
            else:
                chat.message_history = new_messages

            # Update pydantic_message_history
            chat.pydantic_message_history = chat_completion_node.history

            repository.update(chat)

            output = self.OutputType(response_content=new_messages[-1])
            self.save_output(output)

            return task_context
