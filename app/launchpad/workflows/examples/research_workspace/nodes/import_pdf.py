import asyncio
from hashlib import file_digest
from pathlib import Path
from uuid import uuid4

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..config import UPLOAD_DIR, USE_SAMPLE_MODELS
from ..library import import_papers
from ..observability import stage
from ..pdf import chunk_pdf, first_page_text
from ..publication import (
    extract_publication,
    lookup_publication,
    suggest_title_keywords,
)
from ..schema import ImportEvent, Paper, PdfImportEvent, Publication


def pdf_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


class ImportPdfNode(Node):
    class OutputType(Node.OutputType):
        paper_id: str
        chunks: int
        title: str
        publication: Publication | None
        keywords: list[str]
        replaced: bool = False

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: PdfImportEvent = task_context.event
        run_id = event.paper.pdf_run_id
        path = UPLOAD_DIR / run_id.hex / "paper.pdf" if run_id else Path(event.pdf_path)
        with stage("parse_pdf") as metrics:
            chunks = await asyncio.to_thread(chunk_pdf, path)
            digest = await asyncio.to_thread(pdf_sha256, path)
            first_page = (
                await asyncio.to_thread(first_page_text, path)
                if event.enrich_metadata
                else ""
            )
            metrics["chunks"] = len(chunks)
        with stage("paper_title"):
            title, abstract, publication = await extract_publication(
                event.paper, chunks, first_page=first_page, lookup=event.enrich_metadata
            )
        keywords = event.paper.keywords
        if event.enrich_metadata and not USE_SAMPLE_MODELS:
            with stage("paper_keywords") as metrics:
                keywords = (await suggest_title_keywords(title)).keywords
                metrics["keywords"] = len(keywords)
            with stage("publication") as metrics:
                publication = await lookup_publication(title, publication)
                if publication and publication.venue:
                    metrics["publication"] = publication.venue
                if publication and publication.ccf_rank:
                    metrics["ccf_rank"] = publication.ccf_rank
        paper = Paper(
            **event.paper.model_dump(
                exclude={"title", "id", "abstract", "publication", "keywords"}
            ),
            id=event.paper.id or uuid4().hex,
            title=title,
            abstract=abstract,
            publication=publication,
            keywords=keywords,
            pdf_sha256=digest,
        )
        (paper,), replaced = await import_papers(
            ImportEvent(library=event.library, papers=[paper]),
            chunks,
            match_existing=event.match_existing,
        )
        self.save_output(
            self.OutputType(
                paper_id=paper.id,
                chunks=len(chunks),
                title=title,
                publication=paper.publication,
                keywords=paper.keywords,
                replaced=replaced,
            )
        )
        return task_context
