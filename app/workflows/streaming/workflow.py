from core.schema import WorkflowSchema, NodeConfig
from core.workflow import Workflow
from workflows.streaming.schema import OpenAIChatSchema
from workflows.streaming.nodes.text_streaming_node import TextStreamingNode
from workflows.streaming.nodes.structured_streaming_node import (
    StructuredStreamingNode,
)


class ExampleStreamingWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="",
        event_schema=OpenAIChatSchema,
        start=TextStreamingNode,
        nodes=[
            NodeConfig(
                node=TextStreamingNode,
                connections=[StructuredStreamingNode],
                description="",
            ),
            NodeConfig(
                node=StructuredStreamingNode,
                connections=[],
                description="",
            ),
        ],
    )
