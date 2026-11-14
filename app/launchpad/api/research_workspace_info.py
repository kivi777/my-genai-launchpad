import json
import logging
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import delete, func, select

from launchpad.database.event import Event
from launchpad.database.research_deletion import (
    ImportInProgressError,
    PaperChangedError,
    delete_paper,
)
from launchpad.database.research_paper import ResearchPaper
from launchpad.database.session import SessionLocal
from launchpad.workflows.examples import research_workspace
from launchpad.workflows.examples.research_workspace import config
from launchpad.workflows.examples.research_workspace.schema import (
    Keywords,
    LibraryName,
    PaperId,
    Publication,
)

router = APIRouter()
logger = logging.getLogger(__name__)
WORKSPACE = Path(research_workspace.__file__).parent
PAGE_SIZE = 15


class ResourcePreview(BaseModel):
    id: str
    title: str
    pdf_id: UUID | None
    source_url: HttpUrl | None
    keywords: Keywords
    publication: Publication | None


class LibraryPreview(BaseModel):
    total: int
    papers: list[ResourcePreview]
    paper_count: int
    notion_count: int
    has_more: bool


@router.get("/library/{library}")
def library_preview(
    library: LibraryName,
    kind: Literal["paper", "notion"] = "paper",
    page: int = Query(default=1, ge=1, le=100_000),
) -> LibraryPreview:
    if config.DEMO_MODE:
        raise HTTPException(503, "当前演示模式未连接资料库。")
    papers = ResearchPaper.__table__
    title = func.coalesce(
        papers.c.payload["title"].astext,
        papers.c.paper_id,
    )
    source_kind = func.coalesce(papers.c.payload["source_kind"].astext, "paper")
    library_scope = papers.c.library == library
    with SessionLocal() as session:
        counts = dict(
            session.execute(
                select(source_kind, func.count())
                .where(library_scope)
                .group_by(source_kind)
            )
            .tuples()
            .all()
        )
        rows = session.execute(
            select(
                papers.c.paper_id.label("id"),
                title.label("title"),
                papers.c.payload["pdf_run_id"].astext.label("pdf_id"),
                papers.c.payload["source_url"].astext.label("source_url"),
                papers.c.payload["keywords"].label("keywords"),
                papers.c.payload["publication"].label("publication"),
            )
            .where(library_scope, source_kind == kind)
            .order_by(title, papers.c.paper_id)
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE + 1)
        ).mappings()
        previews = [
            ResourcePreview.model_validate(
                dict(row) | {"keywords": row["keywords"] or []}
            )
            for row in rows
        ]
    return LibraryPreview(
        total=counts.get(kind, 0),
        paper_count=counts.get("paper", 0),
        notion_count=counts.get("notion", 0),
        papers=previews[:PAGE_SIZE],
        has_more=len(previews) > PAGE_SIZE,
    )


@router.delete("/library/{library}/papers", status_code=204)
def remove_paper(
    library: LibraryName, paper_id: PaperId, pdf_id: UUID | None = None
) -> Response:
    if config.DEMO_MODE:
        raise HTTPException(503, "当前演示模式未连接资料库。")
    try:
        delete_paper(library, paper_id, pdf_id)
    except PaperChangedError as exc:
        raise HTTPException(409, "文献版本已变化，请刷新后重试。") from exc
    except ImportInProgressError as exc:
        raise HTTPException(409, "这篇文献仍有导入任务在处理，请稍后再试。") from exc
    except OSError as exc:
        logger.exception("research_paper_file_delete_failed")
        raise HTTPException(500, "PDF 文件清理失败，请重试。") from exc
    return Response(status_code=204)


@router.delete("/library/{library}/notes", status_code=204)
def remove_notion_note(library: LibraryName, paper_id: PaperId) -> Response:
    if config.DEMO_MODE:
        raise HTTPException(503, "当前演示模式未连接资料库。")
    with SessionLocal.begin() as session:
        removed = session.execute(
            delete(ResearchPaper)
            .where(
                ResearchPaper.library == library,
                ResearchPaper.paper_id == paper_id,
                ResearchPaper.payload["source_kind"].astext == "notion",
            )
            .returning(ResearchPaper.paper_id)
        ).scalar_one_or_none()
        if removed is not None:
            event_id = func.coalesce(
                Event.data["resource_id"].as_string(),
                "notion:" + Event.data["page_id"].as_string(),
            )
            session.execute(
                delete(Event).where(
                    Event.workflow_type == "RESEARCH_NOTION",
                    Event.data["library"].as_string() == library,
                    event_id == paper_id,
                    Event.task_context.is_not(None),
                )
            )
    return Response(status_code=204)


@router.get("/skill")
def download_skill() -> FileResponse:
    path = WORKSPACE / "skills" / "research-reading" / "SKILL.md"
    return FileResponse(path, filename="SKILL.md", media_type="text/markdown")


@router.get("/integrations")
def integration_settings() -> dict:
    sample = json.loads((WORKSPACE / "request_examples" / "mcp.json").read_text())
    sample["mcpServers"]["research-library"]["env"] = {
        "RESEARCH_API_URL": config.API_URL
    }
    return {
        "mcp_config": sample,
        "external_search_configured": bool(
            config.EXTERNAL_MCP_URL and config.EXTERNAL_MCP_TOOL
        ),
        "ppt_transport": "http" if config.PPT_MCP_URL else "stdio",
    }
