import re
from uuid import uuid4

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..library import import_papers
from ..notion import load_notion_note
from ..observability import stage
from ..schema import (
    ImportEvent,
    NotionPageImportEvent,
    NotionWorkflowEvent,
    Paper,
    PaperChunk,
)


def split_markdown(markdown: str) -> list[PaperChunk]:
    chunks = []
    heading = []
    for section in re.split(r"(?m)(?=^#{1,6}\s)", markdown):
        lines = section.strip().splitlines()
        if not lines:
            continue
        match = re.match(r"^#{1,6}\s+(.+)$", lines[0])
        if match:
            heading = [match.group(1)]
        text = "\n".join(lines[1:] if match and len(lines) > 1 else lines)
        for offset in range(0, len(text), 1000):
            part = text[offset : offset + 1000].strip()
            if part:
                chunks.append(
                    PaperChunk(number=len(chunks) + 1, text=part, headings=heading)
                )
    return chunks


class ImportNotionNode(Node):
    class OutputType(Node.OutputType):
        note_id: str
        chunks: int

    async def process(self, task_context: TaskContext) -> TaskContext:
        incoming: NotionWorkflowEvent = task_context.event
        event = incoming.root
        if isinstance(event, NotionPageImportEvent):
            with stage("fetch_notion_page"):
                event = await load_notion_note(event)
        note = Paper(
            id=event.resource_id or f"notion:{event.page_id or uuid4()}",
            title=event.title,
            source_kind="notion",
            source_url=event.source_url,
            notion_parent=event.notion_parent,
            keywords=event.keywords,
        )
        with stage("split_markdown") as metrics:
            chunks = split_markdown(event.markdown)
            metrics["chunks"] = len(chunks)
        await import_papers(
            ImportEvent(library=event.library, papers=[note]),
            chunks,
            notion_markdown=event.markdown,
        )
        self.save_output(self.OutputType(note_id=note.id, chunks=len(chunks)))
        return task_context
