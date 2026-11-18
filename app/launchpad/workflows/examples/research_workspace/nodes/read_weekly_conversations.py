import asyncio
from datetime import timedelta
from zoneinfo import ZoneInfo

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext
from launchpad.database.research_weekly import weekly_conversation_messages

from ..observability import stage
from ..schema import ConversationMessage

ZONE = ZoneInfo("Asia/Shanghai")


class ReadWeeklyConversationsNode(Node):
    class OutputType(Node.OutputType):
        messages: list[ConversationMessage]

    async def process(self, task_context: TaskContext) -> TaskContext:
        event = task_context.event
        with stage("filter_weekly_messages") as metrics:
            messages = event.messages
            if messages is None:
                messages = await asyncio.to_thread(weekly_conversation_messages, event)
            end = event.week_end + timedelta(days=1)
            selected = sorted(
                (
                    item
                    for item in messages
                    if event.week_start <= item.timestamp.astimezone(ZONE).date() < end
                ),
                key=lambda item: item.timestamp,
            )
            metrics.update(
                messages=len(selected),
                conversations=len(
                    {item.conversation_id for item in selected if item.conversation_id}
                ),
            )
        self.save_output(self.OutputType(messages=selected))
        return task_context
