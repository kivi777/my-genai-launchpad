from launchpad.core.schema import NodeConfig, WorkflowSchema
from launchpad.core.workflow import Workflow
from launchpad.workflows.examples.decision.nodes.decide_team_node import DecideTeamNode
from launchpad.workflows.examples.decision.schema import TicketEvent


class DecisionWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="Choose a support team with Jev and validate the decision.",
        event_schema=TicketEvent,
        start=DecideTeamNode,
        nodes=[NodeConfig(node=DecideTeamNode)],
    )
