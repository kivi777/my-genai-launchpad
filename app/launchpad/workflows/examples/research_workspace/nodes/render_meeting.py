import sys

from mcp import Client, StdioServerParameters

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from .. import config
from ..schema import PresentationResult
from .plan_meeting import PlanMeetingNode
from .read_experiments import ReadExperimentsNode
from .retrieve_papers import RetrievePapersNode


class RenderMeetingNode(Node):
    async def process(self, task_context: TaskContext) -> TaskContext:
        server = config.PPT_MCP_URL or StdioServerParameters(
            command=sys.executable,
            args=["-m", "launchpad.workflows.examples.research_workspace.ppt_tool"],
            env={"RESEARCH_PPT_OUTPUT_DIR": config.PPT_OUTPUT_DIR},
        )
        async with Client(server, read_timeout_seconds=120) as client:
            result = await client.call_tool(
                "render_meeting_pptx",
                {
                    "outline": self.get_output(PlanMeetingNode).model_dump(mode="json"),
                    "experiment": self.get_output(ReadExperimentsNode).model_dump(
                        mode="json"
                    ),
                    "evidence": [
                        hit.model_dump(mode="json")
                        for hit in self.get_output(RetrievePapersNode).hits
                    ],
                },
            )
        if result.is_error:
            raise RuntimeError("Presentation MCP tool failed")
        self.save_output(PresentationResult.model_validate(result.structured_content))
        return task_context
