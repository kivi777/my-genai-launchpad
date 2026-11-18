from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..library import selected_meeting_notes
from ..schema import MeetingNote, SearchHit


class ReadMeetingNotesNode(Node):
    class OutputType(Node.OutputType):
        notes: list[MeetingNote]

        def source_hits(self) -> list[SearchHit]:
            return [SearchHit(paper=note.paper, score=0) for note in self.notes]

    async def process(self, task_context: TaskContext) -> TaskContext:
        notes = await selected_meeting_notes(task_context.event)
        self.save_output(self.OutputType(notes=notes))
        return task_context
