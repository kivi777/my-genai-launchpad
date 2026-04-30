from launchpad.core.schema import NodeConfig, WorkflowSchema
from launchpad.core.workflow import Workflow
from launchpad.workflows.examples.nested_customer_care.nodes.run_reply_workflow_node import (
    RunReplyWorkflowNode,
)
from launchpad.workflows.examples.nested_customer_care.nodes.send_reply_node import (
    SendReplyNode,
)
from launchpad.workflows.examples.nested_customer_care.schema import (
    NestedCustomerCareEventSchema,
)


class NestedCustomerCareWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="Parent workflow that delegates reply drafting to a child workflow.",
        event_schema=NestedCustomerCareEventSchema,
        start=RunReplyWorkflowNode,
        nodes=[
            NodeConfig(
                node=RunReplyWorkflowNode,
                connections=[SendReplyNode],
                description="Calls ReplyDraftWorkflow with the shared context.",
            ),
        ],
    )
