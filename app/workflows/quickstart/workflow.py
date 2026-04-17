from core.schema import WorkflowSchema, NodeConfig
from core.workflow import Workflow
from workflows.quickstart.schema import CustomerCareEventSchema
from workflows.quickstart.nodes.analyze_ticket_node import AnalyzeTicketNode
from workflows.quickstart.nodes.close_ticket_node import CloseTicketNode
from workflows.quickstart.nodes.determine_intent_ticket_node import (
    DetermineTicketIntentNode,
)
from workflows.quickstart.nodes.escalate_ticket_node import EscalateTicketNode
from workflows.quickstart.nodes.filter_spam import FilterSpamNode
from workflows.quickstart.nodes.generate_response_node import GenerateResponseNode
from workflows.quickstart.nodes.process_invoice_node import ProcessInvoiceNode
from workflows.quickstart.nodes.send_reply_node import SendReplyNode
from workflows.quickstart.nodes.ticket_router_node import TicketRouterNode
from workflows.quickstart.nodes.validate_ticket_node import ValidateTicketNode


class CustomerCareWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="",
        event_schema=CustomerCareEventSchema,
        start=AnalyzeTicketNode,
        nodes=[
            NodeConfig(
                node=AnalyzeTicketNode,
                connections=[TicketRouterNode],
                description="",
                concurrent_nodes=[
                    DetermineTicketIntentNode,
                    FilterSpamNode,
                    ValidateTicketNode,
                ],
            ),
            NodeConfig(
                node=TicketRouterNode,
                connections=[
                    CloseTicketNode,
                    EscalateTicketNode,
                    GenerateResponseNode,
                    ProcessInvoiceNode,
                ],
                description="",
                is_router=True,
            ),
            NodeConfig(
                node=GenerateResponseNode,
                connections=[SendReplyNode],
                description="",
            ),
        ],
    )
