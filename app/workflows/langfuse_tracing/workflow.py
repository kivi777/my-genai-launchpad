from core.schema import WorkflowSchema, NodeConfig
from core.workflow import Workflow
from workflows.langfuse_tracing.schema import LangfuseTracingEventSchema
from workflows.langfuse_tracing.nodes.context_summary_result_node import (
    ContextSummaryResult,
)
from workflows.langfuse_tracing.nodes.remove_comment_node import RemoveCommentNode
from workflows.langfuse_tracing.nodes.violation_detection_node import (
    ViolationDetectionNode,
)


class LangfuseTracingWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="",
        event_schema=LangfuseTracingEventSchema,
        start=ViolationDetectionNode,
        nodes=[
            NodeConfig(
                node=ViolationDetectionNode,
                connections=[ContextSummaryResult],
                description="",
            ),
            NodeConfig(
                node=ContextSummaryResult,
                connections=[RemoveCommentNode],
                description="",
            ),
            NodeConfig(
                node=RemoveCommentNode,
                connections=[],
                description="",
            ),
        ],
    )
