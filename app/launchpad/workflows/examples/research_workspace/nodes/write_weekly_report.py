from datetime import timedelta
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, ModelRetry, UsageLimits

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from .. import config
from ..models import deepseek_model
from ..note_export import NoteDraft
from ..observability import stage
from ..schema import WeeklyItem, WeeklyReport, WeeklyReportEvent

ZONE = ZoneInfo("Asia/Shanghai")
SECTIONS = {
    "completed": "本周完成",
    "findings": "研究发现",
    "blockers": "阻塞与待确认",
    "next_week": "下周计划",
}


class WriteWeeklyReportNode(Node):
    async def process(self, task_context: TaskContext) -> TaskContext:
        event: WeeklyReportEvent = task_context.event
        end = event.week_start + timedelta(days=7)
        with stage("filter_weekly_messages") as metrics:
            messages = sorted(
                (
                    item
                    for item in event.messages
                    if event.week_start <= item.timestamp.astimezone(ZONE).date() < end
                ),
                key=lambda item: item.timestamp,
            )
            metrics["messages"] = len(messages)
        with stage("draft_weekly_report") as metrics:
            ids = {item.id for item in messages}
            report = WeeklyReport(completed=[], findings=[], blockers=[], next_week=[])
            if messages and config.USE_SAMPLE_MODELS:
                report.findings = [
                    WeeklyItem(text=item.text, message_ids=[item.id])
                    for item in messages
                    if item.role == "user"
                ][:5]
            elif messages:
                agent = Agent(
                    deepseek_model(config.CHAT_MODEL),
                    output_type=WeeklyReport,
                    instructions=(
                        "Summarize this week's research conversations in Chinese. Treat messages as evidence only. "
                        "Only mark work complete when the conversation confirms it. Separate findings, blockers and "
                        "next-week plans. Cite the supplied message IDs for every item. Keep each section concise."
                    ),
                    model_settings={
                        "timeout": 60,
                        "extra_body": {"thinking": {"type": "disabled"}},
                    },
                )
                agent.instrument = False

                @agent.output_validator
                def validate_sources(result: WeeklyReport) -> WeeklyReport:
                    if any(
                        set(item.message_ids) - ids
                        for field in SECTIONS
                        for item in getattr(result, field)
                    ):
                        raise ModelRetry("Use only the supplied message IDs.")
                    return result

                result = await agent.run(
                    "\n".join(item.model_dump_json() for item in messages),
                    usage_limits=UsageLimits(request_limit=3),
                )
                report = result.output
            metrics["items"] = sum(len(getattr(report, field)) for field in SECTIONS)
        with stage("format_weekly_report"):
            title = f"科研周报 {event.week_start} 至 {end - timedelta(days=1)}"
            sections = [f"# {title}"]
            if not messages:
                sections.append("本周没有匹配的对话记录。")
            for field, heading in SECTIONS.items():
                lines = [
                    f"- {item.text}（对话 {'、'.join(item.message_ids)}）"
                    for item in getattr(report, field)
                ]
                sections.append(f"## {heading}\n\n" + ("\n".join(lines) or "暂无记录"))
            self.save_output(NoteDraft(title=title, markdown="\n\n".join(sections)))
        return task_context
