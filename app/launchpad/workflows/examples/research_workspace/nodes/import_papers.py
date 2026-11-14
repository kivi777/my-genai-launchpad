from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..library import import_papers


class ImportPapersNode(Node):
    class OutputType(Node.OutputType):
        library: str
        imported: int

    async def process(self, task_context: TaskContext) -> TaskContext:
        event = task_context.event
        await import_papers(event)
        self.save_output(
            self.OutputType(library=event.library, imported=len(event.papers))
        )
        return task_context
