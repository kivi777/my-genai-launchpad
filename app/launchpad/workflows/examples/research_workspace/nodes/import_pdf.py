import asyncio
from pathlib import Path
from uuid import uuid4

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..config import UPLOAD_DIR
from ..library import import_papers
from ..observability import stage
from ..pdf import chunk_pdf
from ..publication import extract_publication
from ..schema import ImportEvent, Paper, PdfImportEvent, Publication


class ImportPdfNode(Node):
    class OutputType(Node.OutputType):
        paper_id: str
        chunks: int
        title: str
        publication: Publication | None
        keywords: list[str]

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: PdfImportEvent = task_context.event
        run_id = event.paper.pdf_run_id
        path = UPLOAD_DIR / run_id.hex / "paper.pdf" if run_id else Path(event.pdf_path)
        with stage("parse_pdf") as metrics:
            chunks = await asyncio.to_thread(chunk_pdf, path)
            metrics["chunks"] = len(chunks)
        with stage("paper_title"):
            title, abstract, publication = await extract_publication(
                event.paper, chunks
            )
        paper = Paper(
            **event.paper.model_dump(
                exclude={"title", "id", "abstract", "publication"}
            ),
            id=event.paper.id or uuid4().hex,
            title=title,
            abstract=abstract,
            publication=publication,
        )
        await import_papers(ImportEvent(library=event.library, papers=[paper]), chunks)
        self.save_output(
            self.OutputType(
                paper_id=paper.id,
                chunks=len(chunks),
                title=title,
                publication=publication,
                keywords=paper.keywords,
            )
        )
        return task_context
