import sys

from mcp import Client, StdioServerParameters

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from .. import config
from ..schema import PresentationResult
from .plan_meeting import PlanMeetingNode
from .read_experiments import ReadExperimentsNode
from .read_meeting_notes import ReadMeetingNotesNode
from .retrieve_papers import RetrievePapersNode


class RenderMeetingNode(Node):
    async def process(self, task_context: TaskContext) -> TaskContext:
        academic_layout = task_context.event.uses_academic_layout
        remote = None if academic_layout else config.PPT_MCP_URL
        server = remote or StdioServerParameters(
            command=sys.executable,
            args=["-m", "launchpad.workflows.examples.research_workspace.ppt_tool"],
            env={"RESEARCH_PPT_OUTPUT_DIR": config.PPT_OUTPUT_DIR},
        )
        outline = self.get_output(PlanMeetingNode)
        experiment = self.get_output(ReadExperimentsNode)
        selected = self.get_output(ReadMeetingNotesNode)
        retrieved = self.get_output(RetrievePapersNode)
        sources = retrieved.hits if retrieved else selected.source_hits()
        arguments = {
            "outline": outline.model_dump(
                mode="json",
                exclude={"theme": True}
                if academic_layout
                else {"theme": True, "slides": {"__all__": {"purpose"}}},
            ),
            "experiment": experiment.model_dump(mode="json") if experiment else None,
            "evidence": [hit.model_dump(mode="json") for hit in sources],
        }
        async with Client(server, read_timeout_seconds=120) as client:
            if academic_layout:
                arguments["academic_layout"] = True
            if outline.theme:
                if remote:
                    listing = await client.list_tools()
                    if not any(
                        tool.name == "render_meeting_pptx"
                        and "theme" in tool.input_schema.get("properties", {})
                        for tool in listing.tools
                    ):
                        raise ValueError("当前 PPT MCP 服务未提供 theme 参数。")
                arguments["theme"] = outline.theme.model_dump(mode="json")
            result = await client.call_tool("render_meeting_pptx", arguments)
        if result.is_error:
            if academic_layout and result.content and result.content[0].type == "text":
                raise ValueError(result.content[0].text)
            raise RuntimeError("Presentation MCP tool failed")
        self.save_output(PresentationResult.model_validate(result.structured_content))
        return task_context
