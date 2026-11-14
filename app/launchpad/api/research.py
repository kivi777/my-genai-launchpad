import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from launchpad.api.research_conversations import router as conversation_router
from launchpad.api.research_reader import router as reader_router
from launchpad.api.research_workspace_info import router as workspace_info_router
from launchpad.workflows.examples.research_workspace import config
from launchpad.workflows.examples.research_workspace.jobs import (
    ConversationLibraryError,
    ConversationNotFoundError,
    DispatchError,
    ResearchJob,
    get_job,
    recent_jobs,
    submit_job,
)
from launchpad.workflows.examples.research_workspace.publication import (
    KeywordPreview,
    preview_publication,
    suggest_pdf_keywords,
)
from launchpad.workflows.examples.research_workspace.schema import (
    ImportEvent,
    LibraryName,
    MeetingEvent,
    NotionImportEvent,
    PdfImportEvent,
    PdfMetadata,
    Publication,
    ResearchEvent,
    SearchEvent,
    TranslationEvent,
    WeeklyReportEvent,
)
from launchpad.workflows.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(reader_router)
router.include_router(conversation_router)
router.include_router(workspace_info_router)


class ImportRequest(ImportEvent):
    action: Literal["import_papers"]


class ReadingRequest(SearchEvent):
    action: Literal["reading_note"]
    conversation_id: UUID | None = None
    start_conversation: bool = False


class SearchRequest(SearchEvent):
    action: Literal["search"]
    conversation_id: UUID | None = None
    start_conversation: bool = False


class WeeklyRequest(WeeklyReportEvent):
    action: Literal["weekly_report"]


class NotionImportRequest(NotionImportEvent):
    action: Literal["import_notion"]


class TranslationJobRequest(TranslationEvent):
    action: Literal["translate"]


class ResearchStreamEvent(BaseModel):
    run_id: str
    trace_id: str | None = None
    demo: bool
    outputs: dict | None = None
    message: str | None = None


async def event_stream(
    request: ResearchEvent, entry: WorkflowRegistry
) -> AsyncIterator[str]:
    run_id = uuid4().hex
    yield f"event: accepted\ndata: {ResearchStreamEvent(run_id=run_id, demo=config.DEMO_MODE).model_dump_json(exclude_none=True)}\n\n"
    try:
        workflow = await asyncio.to_thread(entry.value)
        task = asyncio.create_task(
            workflow.run_async(request.model_dump(exclude={"action"}))
        )
        try:
            while not task.done():
                done, _ = await asyncio.wait([task], timeout=10)
                if not done:
                    yield ": heartbeat\n\n"
            context = task.result()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        payload = ResearchStreamEvent(
            run_id=run_id,
            trace_id=context.trace_id,
            demo=config.DEMO_MODE,
            outputs=context.nodes,
        )
        yield f"event: completed\ndata: {payload.model_dump_json(exclude_none=True)}\n\n"
    except Exception:
        logger.exception("research_run_failed", extra={"run_id": run_id})
        payload = ResearchStreamEvent(
            run_id=run_id,
            demo=config.DEMO_MODE,
            message="Research workflow failed. See server logs.",
        )
        yield f"event: failed\ndata: {payload.model_dump_json(exclude_none=True)}\n\n"


@router.post("/events", status_code=202, response_model=None)
async def research_events(
    request: Annotated[
        ImportRequest
        | ReadingRequest
        | SearchRequest
        | WeeklyRequest
        | NotionImportRequest
        | TranslationJobRequest,
        Body(discriminator="action"),
    ],
) -> JSONResponse | StreamingResponse:
    entry = {
        "import_papers": WorkflowRegistry.RESEARCH_IMPORT,
        "reading_note": WorkflowRegistry.RESEARCH_READING,
        "search": WorkflowRegistry.RESEARCH_SEARCH,
        "weekly_report": WorkflowRegistry.RESEARCH_WEEKLY,
        "import_notion": WorkflowRegistry.RESEARCH_NOTION,
        "translate": WorkflowRegistry.RESEARCH_TRANSLATE,
    }[request.action]
    if isinstance(request, (ReadingRequest, SearchRequest)):
        if request.start_conversation and request.conversation_id is not None:
            raise HTTPException(422, "新会话无需提供已有会话 ID。")
        event = SearchEvent.model_validate(
            request.model_dump(
                exclude={
                    "action",
                    "conversation_id",
                    "start_conversation",
                    "previous_turns",
                }
            )
        )
        return await dispatch(
            event,
            entry,
            conversation_id=request.conversation_id,
            start_conversation=request.start_conversation,
        )
    return await dispatch(request, entry)


async def dispatch(
    request: ResearchEvent,
    entry: WorkflowRegistry,
    run_id: UUID | None = None,
    *,
    conversation_id: UUID | None = None,
    start_conversation: bool = False,
) -> JSONResponse | StreamingResponse:
    if config.DEMO_MODE:
        return stream_response(event_stream(request, entry))
    try:
        job = await asyncio.to_thread(
            submit_job,
            request,
            entry,
            run_id,
            conversation_id=conversation_id,
            start_conversation=start_conversation,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(404, "会话不存在。") from exc
    except ConversationLibraryError as exc:
        raise HTTPException(
            409, "该会话已绑定资料库，请新建会话后切换资料库。"
        ) from exc
    except DispatchError as exc:
        logger.exception("research_job_dispatch_failed")
        raise HTTPException(
            503, {"run_id": str(exc.run_id), "message": str(exc)}
        ) from exc
    status_url = f"/research/jobs/{job.run_id}"
    return JSONResponse(
        job.model_dump(mode="json", exclude_none=True) | {"status_url": status_url},
        status_code=202,
        headers={"Location": status_url},
    )


@router.get("/jobs")
def research_jobs(
    library: LibraryName, workspace: Literal["pdf", "notion", "weekly", "meeting"]
) -> list[ResearchJob]:
    if config.DEMO_MODE:
        return []
    workflow = {
        "pdf": WorkflowRegistry.RESEARCH_PDF,
        "notion": WorkflowRegistry.RESEARCH_NOTION,
        "weekly": WorkflowRegistry.RESEARCH_WEEKLY,
        "meeting": WorkflowRegistry.RESEARCH_MEETING,
    }[workspace]
    return recent_jobs(library, workflow)


@router.get("/jobs/{run_id}")
async def research_job(run_id: UUID) -> dict:
    job = await asyncio.to_thread(get_job, run_id)
    if job is None:
        raise HTTPException(404, "Research job not found")
    return job.model_dump(mode="json", exclude_none=True)


def save_upload(run_id: UUID, filename: str, content: bytes) -> str:
    directory = config.UPLOAD_DIR / run_id.hex
    directory.mkdir(parents=True)
    path = directory / filename
    path.write_bytes(content)
    return str(path)


def stream_response(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class PdfPreviewRequest(BaseModel):
    first_pages: Annotated[str, Field(min_length=1, max_length=12000)]


class PdfPublicationPreview(BaseModel):
    publication: Publication | None


@router.post("/pdf-keywords")
async def pdf_keywords(request: PdfPreviewRequest) -> KeywordPreview:
    if config.USE_SAMPLE_MODELS or not config.DEEPSEEK_API_KEY:
        raise HTTPException(503, "自动生成关键词需要配置 DeepSeek。")
    try:
        return await suggest_pdf_keywords(request.first_pages)
    except Exception as exc:
        logger.warning(
            "research_pdf_keyword_preview_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(502, "关键词生成失败，请重试。") from exc


@router.post("/pdf-publication")
async def pdf_publication(request: PdfPreviewRequest) -> PdfPublicationPreview:
    if config.USE_SAMPLE_MODELS or not config.DEEPSEEK_API_KEY:
        raise HTTPException(503, "查询发表渠道需要配置 DeepSeek。")
    try:
        return PdfPublicationPreview(
            publication=await preview_publication(request.first_pages)
        )
    except Exception as exc:
        logger.warning(
            "research_pdf_publication_preview_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(502, "发表信息查询失败，请重试。") from exc


@router.post("/pdf", status_code=202, response_model=None)
async def research_pdf(
    file: UploadFile,
    library: Annotated[LibraryName, Form()],
    paper: Annotated[str, Form(description="Paper metadata as JSON")],
) -> JSONResponse | StreamingResponse:
    try:
        metadata = PdfMetadata.model_validate_json(paper).model_copy(
            update={"pdf_run_id": None}
        )
    except ValidationError as exc:
        raise HTTPException(422, "Invalid paper metadata") from exc

    pdf = await file.read(30 * 1024 * 1024 + 1)
    if len(pdf) > 30 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds 30 MiB")
    if not pdf.startswith(b"%PDF-"):
        raise HTTPException(422, "Expected a PDF upload")

    if not config.DEMO_MODE:
        run_id = uuid4()
        path = await asyncio.to_thread(save_upload, run_id, "paper.pdf", pdf)
        request = PdfImportEvent(
            library=library,
            paper=metadata.model_copy(update={"pdf_run_id": run_id}),
            pdf_path=path,
        )
        return await dispatch(request, WorkflowRegistry.RESEARCH_PDF, run_id)

    async def import_pdf() -> AsyncIterator[str]:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "paper.pdf"
            await asyncio.to_thread(path.write_bytes, pdf)
            request = PdfImportEvent(
                library=library, paper=metadata, pdf_path=str(path)
            )
            async for event in event_stream(request, WorkflowRegistry.RESEARCH_PDF):
                yield event

    return stream_response(import_pdf())


@router.post("/meeting", status_code=202, response_model=None)
async def research_meeting(
    file: UploadFile,
    library: Annotated[LibraryName, Form()],
    query: Annotated[str, Form(min_length=1, max_length=1000)],
    worksheet: Annotated[str, Form(min_length=1, max_length=31)],
    category_column: Annotated[str, Form(min_length=1, max_length=100)],
    value_column: Annotated[str, Form(min_length=1, max_length=100)],
    weekly_report: Annotated[str | None, Form(min_length=1, max_length=30000)] = None,
    weekly_run_id: Annotated[UUID | None, Form()] = None,
) -> JSONResponse | StreamingResponse:
    if weekly_run_id is not None and weekly_report is not None:
        raise HTTPException(422, "Provide weekly_report or weekly_run_id")
    if weekly_run_id is not None:
        report = await asyncio.to_thread(get_job, weekly_run_id, library=library)
        weekly_report = (
            (report.outputs or {}).get("WriteWeeklyReportNode", {}).get("markdown")
            if report
            else None
        )
    if not weekly_report or not weekly_report.strip():
        raise HTTPException(
            422, "Provide Markdown or a completed weekly report ID for this library"
        )
    if len(weekly_report) > 30000:
        raise HTTPException(422, "Weekly report exceeds 30,000 characters")
    workbook = await file.read(10 * 1024 * 1024 + 1)
    if len(workbook) > 10 * 1024 * 1024:
        raise HTTPException(413, "Workbook exceeds 10 MiB")
    if not (file.filename or "").lower().endswith(".xlsx") or not workbook.startswith(
        b"PK"
    ):
        raise HTTPException(422, "Expected an XLSX workbook")
    if not query.strip():
        raise HTTPException(422, "Query must not be blank")

    def meeting_event(path: str) -> MeetingEvent:
        return MeetingEvent(
            library=library,
            query=query,
            weekly_report=weekly_report,
            workbook_path=path,
            worksheet=worksheet,
            category_column=category_column,
            value_column=value_column,
        )

    if not config.DEMO_MODE:
        run_id = uuid4()
        path = await asyncio.to_thread(save_upload, run_id, "experiment.xlsx", workbook)
        return await dispatch(
            meeting_event(path), WorkflowRegistry.RESEARCH_MEETING, run_id
        )

    async def run_meeting() -> AsyncIterator[str]:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.xlsx"
            await asyncio.to_thread(path.write_bytes, workbook)
            async for message in event_stream(
                meeting_event(str(path)), WorkflowRegistry.RESEARCH_MEETING
            ):
                yield message

    return stream_response(run_meeting())


@router.get("/decks/{filename}", response_class=FileResponse)
async def research_deck(filename: str) -> FileResponse:
    try:
        artifact_id = UUID(filename.removesuffix(".pptx")).hex
        if filename != f"{artifact_id}.pptx":
            raise ValueError
    except ValueError as exc:
        raise HTTPException(404, "Presentation not found") from exc
    path = Path(config.PPT_OUTPUT_DIR) / filename
    if not path.is_file():
        raise HTTPException(404, "Presentation not found")
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@router.get("/pdf/{run_id}", response_class=FileResponse)
async def research_source_pdf(run_id: UUID) -> FileResponse:
    path = config.UPLOAD_DIR / run_id.hex / "paper.pdf"
    if not path.is_file():
        raise HTTPException(404, "PDF not found")
    return FileResponse(path, media_type="application/pdf")


@router.get("/health")
async def research_health() -> dict[str, str]:
    mode = (
        "memory" if config.DEMO_MODE else "offline" if config.OFFLINE_MODE else "live"
    )
    return {"status": "ready", "mode": mode}


class TranslationRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=12000)]


@router.post("/translate")
async def research_translate(request: TranslationRequest) -> dict[str, str]:
    if config.USE_SAMPLE_MODELS or not config.DEEPSEEK_API_KEY:
        raise HTTPException(503, "翻译需要正式模式和已配置的 DeepSeek 密钥。")

    from launchpad.workflows.examples.research_workspace.nodes.translate_passage import (
        translate_passage,
    )

    try:
        translation = await translate_passage(request.text)
    except Exception as exc:
        logger.warning("research_translation_failed", exc_info=True)
        raise HTTPException(502, "翻译服务暂不可用，请重试。") from exc
    return {"translation": translation}
