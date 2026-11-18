import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import UUID

import httpx
from langfuse import Langfuse, get_client, propagate_attributes
from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, ValidationError
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from launchpad.database.event import Event
from launchpad.database.research_repository import MeetingSourceUnavailable
from launchpad.database.session import SessionLocal

from . import config
from .notion import NotionError

logger = logging.getLogger(__name__)

Metric = int | str
JobStatus = Literal["queued", "running", "completed", "failed"]

STEP_LABELS = {
    "dispatch": "提交到任务队列",
    "TranslatePassageNode": "翻译 PDF 片段",
    "initialize": "初始化工作流",
    "ImportPdfNode": "导入 PDF",
    "ImportNotionNode": "导入 Notion 笔记",
    "ImportPapersNode": "导入论文摘要",
    "parse_pdf": "解析 PDF 并切片",
    "paper_title": "提取论文原题与摘要",
    "paper_keywords": "按论文标题生成中文关键词",
    "publication": "核对论文发表渠道与等级",
    "split_markdown": "解析笔记并切片",
    "fetch_notion_page": "从 Notion 读取页面",
    "embed_documents": "生成文档向量",
    "store_documents": "写入 PostgreSQL",
    "PlanRetrievalNode": "分析问题与规划检索",
    "RetrievePapersNode": "检索资料",
    "embed_query": "生成查询向量",
    "hybrid_search": "执行混合检索",
    "WriteReadingNoteNode": "生成回答与原文引用",
    "external_tool": "调用外部检索 MCP",
    "WriteWeeklyReportNode": "生成科研周报",
    "ReadWeeklyConversationsNode": "读取会话记录",
    "filter_weekly_messages": "筛选本周对话",
    "draft_weekly_report": "按日期提炼进展与研究关注",
    "format_weekly_report": "生成 Markdown 周报",
    "ReadExperimentsNode": "读取 Excel 实验数据",
    "ReadMeetingNotesNode": "按 ID 读取所选资料",
    "MeetingMaterialsRouter": "选择资料处理方式",
    "PlanMeetingNode": "生成组会大纲",
    "RenderMeetingNode": "调用 PPT MCP 并生成文件",
    "save_result": "保存任务结果",
}


class TaskStep(BaseModel):
    key: str
    label: str
    depth: int
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    duration_ms: int | None = None
    metrics: dict[str, Metric] = Field(default_factory=dict)
    error: str | None = None


class TaskProgress(BaseModel):
    status: JobStatus = "running"
    trace_id: str | None = None
    trace_url: HttpUrl | None = None
    failed_step: str | None = None
    queue_ms: int | None = None
    message: str | None = None
    steps: list[TaskStep] = Field(default_factory=list)


def failure_reason(exc: Exception, key: str) -> str:
    if isinstance(exc, (NotionError, MeetingSourceUnavailable)):
        return str(exc)
    if isinstance(exc, (httpx.HTTPStatusError, ModelHTTPError)):
        status = (
            exc.response.status_code
            if isinstance(exc, httpx.HTTPStatusError)
            else exc.status_code
        )
        return f"外部服务返回 HTTP {status}。"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "操作超时。"
    if isinstance(exc, httpx.RequestError):
        return "无法连接外部服务。"
    if isinstance(exc, FileNotFoundError):
        return "找不到任务所需的上传文件。"
    if isinstance(exc, SQLAlchemyError):
        return "PostgreSQL 操作失败。"
    if isinstance(exc, UnexpectedModelBehavior):
        return "模型多次未返回符合要求的结构化结果。"
    if key == "ReadExperimentsNode":
        if isinstance(exc, KeyError):
            return "Excel 中找不到指定的工作表。"
        if isinstance(exc, ValueError) and str(exc).startswith(
            (
                "Choose distinct",
                "Worksheet exceeds",
                "Expected a category",
                "Select a chart",
            )
        ):
            return str(exc)
    if (
        key == "parse_pdf"
        and isinstance(exc, ValueError)
        and str(exc) == "Docling could not extract any searchable text from the PDF"
    ):
        return "Docling 未能从 PDF 提取可检索的文字。"
    if key == "embed_documents" or key == "embed_query":
        if str(exc) == "Set SILICONFLOW_API_KEY for research embeddings":
            return "Worker 缺少硅基流动的嵌入服务密钥。"
    if key == "TranslatePassageNode" and not config.DEEPSEEK_API_KEY:
        return "翻译需要配置 DeepSeek 密钥。"
    if key == "RenderMeetingNode":
        return f"PPT MCP 渲染失败（{type(exc).__name__}）。"
    return f"{STEP_LABELS.get(key, key)}失败（{type(exc).__name__}），可用任务 ID 查询 Worker 日志。"


class TaskMonitor:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self.progress = TaskProgress()
        self.client: Langfuse | None = None
        self.depth = 0

    def persist(self) -> None:
        try:
            with SessionLocal.begin() as session:
                session.execute(
                    update(Event)
                    .where(Event.id == self.run_id)
                    .values(
                        research_progress=self.progress.model_dump(
                            mode="json", exclude_none=True
                        ),
                    )
                )
        except SQLAlchemyError as exc:
            logger.warning(
                "research_progress_write_failed",
                extra={"run_id": str(self.run_id), "error_type": type(exc).__name__},
            )

    @contextmanager
    def step(self, key: str) -> Iterator[dict[str, Metric]]:
        item = TaskStep(
            key=key,
            label=STEP_LABELS.get(key, key),
            depth=self.depth,
            status="running",
            started_at=datetime.now(UTC),
        )
        self.progress.steps.append(item)
        self.depth += 1
        self.persist()
        start = monotonic()
        with ExitStack() as stack:
            span = None
            if self.client is not None:
                try:
                    span = stack.enter_context(
                        self.client.start_as_current_observation(name=key)
                    )
                except Exception:
                    logger.warning(
                        "research_stage_trace_unavailable", extra={"stage": key}
                    )
            failure = None
            try:
                yield item.metrics
            except Exception as exc:
                failure = exc
                item.status = "failed"
                item.error = failure_reason(exc, key)
            else:
                item.status = "completed"
            finally:
                self.depth -= 1
                item.duration_ms = round((monotonic() - start) * 1000)
                self.persist()
                if span:
                    try:
                        if failure:
                            span.update(level="ERROR", status_message=item.error)
                        span.update(output=item.metrics)
                    except Exception:
                        logger.warning(
                            "research_stage_trace_update_failed", extra={"stage": key}
                        )
        # Keep raw exceptions out of the SDK span context.
        if failure:
            raise failure

    @contextmanager
    def run(
        self,
        workflow: str,
        conversation_id: UUID | None,
        *,
        queue_ms: int | None = None,
    ) -> Iterator[None]:
        self.progress.queue_ms = queue_ms
        with ExitStack() as stack:
            root = None
            if config.TRACING:
                try:
                    client = get_client()
                    root = stack.enter_context(
                        client.start_as_current_observation(
                            name=workflow,
                            trace_context={"trace_id": self.run_id.hex},
                            metadata={"queue_ms": queue_ms}
                            if queue_ms is not None
                            else None,
                        )
                    )
                    self.client = client
                    self.progress.trace_id = client.get_current_trace_id()
                    stack.enter_context(
                        propagate_attributes(
                            session_id=str(conversation_id)
                            if conversation_id
                            else None,
                            metadata={"run_id": str(self.run_id), "workflow": workflow},
                        )
                    )
                except Exception:
                    logger.warning(
                        "research_trace_unavailable", extra={"run_id": str(self.run_id)}
                    )
            if self.progress.trace_id and self.client and config.LANGFUSE_PROJECT_ID:
                try:
                    url = f"{config.LANGFUSE_BASE_URL.rstrip('/')}/project/{config.LANGFUSE_PROJECT_ID}/traces/{self.progress.trace_id}"
                    self.progress.trace_url = TypeAdapter(HttpUrl).validate_python(url)
                except ValidationError:
                    logger.warning("research_trace_url_invalid")
            self.persist()
            token = current_monitor.set(self)
            failure = None
            try:
                yield
            except Exception as exc:
                failure = exc
                self.progress.status = "failed"
                failed = next(
                    (
                        step
                        for step in reversed(self.progress.steps)
                        if step.status == "failed"
                    ),
                    None,
                )
                self.progress.failed_step = (
                    failed.label if failed else STEP_LABELS["initialize"]
                )
                self.progress.message = (
                    failed.error if failed else failure_reason(exc, "initialize")
                )
            else:
                self.progress.status = "completed"
            finally:
                current_monitor.reset(token)
                if root:
                    try:
                        root.update(
                            output={
                                "status": self.progress.status,
                                "steps": len(self.progress.steps),
                            }
                        )
                        if failure:
                            root.update(
                                level="ERROR", status_message=self.progress.message
                            )
                    except Exception:
                        logger.warning(
                            "research_trace_update_failed",
                            extra={"run_id": str(self.run_id)},
                        )
        if self.progress.trace_id and self.client and not self.progress.trace_url:
            try:
                url = self.client.get_trace_url(trace_id=self.progress.trace_id)
                if url:
                    self.progress.trace_url = TypeAdapter(HttpUrl).validate_python(url)
            except Exception:
                logger.warning(
                    "research_trace_url_unavailable", extra={"run_id": str(self.run_id)}
                )
        self.persist()
        if failure:
            raise failure


current_monitor: ContextVar[TaskMonitor | None] = ContextVar(
    "research_task_monitor", default=None
)


@contextmanager
def stage(key: str) -> Iterator[dict[str, Metric]]:
    monitor = current_monitor.get()
    if monitor is None:
        yield {}
    else:
        with monitor.step(key) as metrics:
            yield metrics
