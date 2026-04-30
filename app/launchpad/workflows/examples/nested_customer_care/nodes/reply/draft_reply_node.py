from pydantic import BaseModel

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext
from launchpad.workflows.examples.nested_customer_care.schema import (
    NestedCustomerCareEventSchema,
)


class DraftReplyNode(Node):
    class OutputType(BaseModel):
        reply: str

    async def process(self, task_context: TaskContext) -> TaskContext:
        event = self._event(task_context)
        self.save_output(
            self.OutputType(
                reply=(
                    f"Hi {event.sender}, thanks for your message about "
                    f"'{event.subject}'. We received it and will follow up soon."
                )
            )
        )
        return task_context

    def _event(self, task_context: TaskContext) -> NestedCustomerCareEventSchema:
        return (
            task_context.event
            if isinstance(task_context.event, NestedCustomerCareEventSchema)
            else NestedCustomerCareEventSchema(**task_context.event)
        )
