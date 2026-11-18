from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, ModelRetry, UsageLimits

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext
from launchpad.services.prompt_loader import PromptManager

from .. import config
from ..models import deepseek_model
from ..note_export import NoteDraft
from ..observability import stage
from ..schema import ConversationMessage, WeeklyItem, WeeklyReport, WeeklyReportEvent
from .read_weekly_conversations import ReadWeeklyConversationsNode

ZONE = ZoneInfo("Asia/Shanghai")
SECTIONS = {
    "completed": "完成与推进",
    "focus": "研究关注",
    "findings": "讨论与发现",
    "blockers": "问题与待确认",
    "next_week": "后续安排",
}


def message_batches(
    messages: list[ConversationMessage],
) -> list[list[ConversationMessage]]:
    batches: list[list[ConversationMessage]] = []
    length = 0
    for message in messages:
        size = len(message.model_dump_json())
        if not batches or length + size > 24000:
            batches.append([])
            length = 0
        batches[-1].append(message)
        length += size
    return batches


def format_weekly_report(
    event: WeeklyReportEvent, messages: list[ConversationMessage], report: WeeklyReport
) -> NoteDraft:
    title = f"科研周报 {event.week_start} 至 {event.week_end}"
    sources = {message.id: message for message in messages}
    conversations = {
        message.conversation_id for message in messages if message.conversation_id
    }
    sections = [
        f"# {title}",
        f"按北京时间整理，共 {len(conversations)} 个会话、{len(messages)} 条消息。日期为会话发生日期。",
    ]
    current = event.week_start
    while current <= event.week_end:
        sections.append(f"## {current.isoformat()}")
        day_messages = [
            message
            for message in messages
            if message.timestamp.astimezone(ZONE).date() == current
        ]
        if not day_messages:
            sections.append("当日无会话记录。")
        else:
            for field, heading in SECTIONS.items():
                lines = []
                seen = set()
                for item in getattr(report, field):
                    source = sources[item.message_ids[0]]
                    if (
                        source.timestamp.astimezone(ZONE).date() != current
                        or item.text in seen
                    ):
                        continue
                    seen.add(item.text)
                    references = list(
                        dict.fromkeys(
                            f"{sources[key].conversation_title or '会话记录'} · {sources[key].timestamp.astimezone(ZONE):%H:%M}"
                            for key in item.message_ids
                        )
                    )
                    lines.append(f"- {item.text}\n  - 来源 · {'；'.join(references)}")
                if lines:
                    sections.append(f"### {heading}\n\n" + "\n".join(lines))
        current += timedelta(days=1)
    return NoteDraft(title=title, markdown="\n\n".join(sections))


class WriteWeeklyReportNode(Node):
    async def process(self, task_context: TaskContext) -> TaskContext:
        event: WeeklyReportEvent = task_context.event
        messages = self.get_output(ReadWeeklyConversationsNode).messages
        report = WeeklyReport(completed=[], findings=[], blockers=[], next_week=[])
        with stage("draft_weekly_report") as metrics:
            if config.USE_SAMPLE_MODELS:
                report.focus = [
                    WeeklyItem(text=message.text, message_ids=[message.id])
                    for message in messages
                    if message.role == "user"
                ]
            elif messages:
                agent = Agent(
                    deepseek_model(config.CHAT_MODEL),
                    output_type=WeeklyReport,
                    instructions=PromptManager.get_prompt(
                        "weekly_report",
                        prompts_dir=Path(__file__).parent.parent / "prompts",
                    ),
                    model_settings={
                        "timeout": 60,
                        "extra_body": {"thinking": {"type": "disabled"}},
                    },
                )
                agent.instrument = task_context.trace_id is not None
                batch_sources: dict[str, ConversationMessage] = {}

                @agent.output_validator
                def validate_sources(result: WeeklyReport) -> WeeklyReport:
                    for field in SECTIONS:
                        for item in getattr(result, field):
                            if set(item.message_ids) - batch_sources.keys():
                                raise ModelRetry("Use only the supplied message IDs.")
                            dates = {
                                batch_sources[key].timestamp.astimezone(ZONE).date()
                                for key in item.message_ids
                            }
                            if len(dates) != 1:
                                raise ModelRetry(
                                    "Each item must refer to exactly one calendar date. Split it by date."
                                )
                            if field in {"completed", "focus", "next_week"} and not any(
                                batch_sources[key].role == "user"
                                for key in item.message_ids
                            ):
                                raise ModelRetry(
                                    "Work, research interests and plans require user-message evidence."
                                )
                    return result

                batches = message_batches(messages)
                metrics["batches"] = len(batches)
                for batch in batches:
                    batch_sources = {message.id: message for message in batch}
                    result = await agent.run(
                        "\n".join(
                            message.model_copy(
                                update={"timestamp": message.timestamp.astimezone(ZONE)}
                            ).model_dump_json()
                            for message in batch
                        ),
                        usage_limits=UsageLimits(request_limit=3),
                    )
                    for field in SECTIONS:
                        getattr(report, field).extend(getattr(result.output, field))
            metrics["items"] = sum(len(getattr(report, field)) for field in SECTIONS)
        with stage("format_weekly_report"):
            self.save_output(format_weekly_report(event, messages, report))
        return task_context
