from core.schema import WorkflowSchema, NodeConfig
from core.workflow import Workflow
from workflows.chat.schema import ChatCompletionEventSchema
from workflows.chat.nodes.chat_completion_node import ChatCompletionNode
from workflows.chat.nodes.prepare_chat_node import PrepareChatNode
from workflows.chat.nodes.update_chat_node import UpdateChatNode


class ChatExampleWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="",
        event_schema=ChatCompletionEventSchema,
        start=PrepareChatNode,
        nodes=[
            NodeConfig(
                node=PrepareChatNode,
                connections=[ChatCompletionNode],
                description="",
            ),
            NodeConfig(
                node=ChatCompletionNode,
                connections=[UpdateChatNode],
                description="",
            ),
            NodeConfig(
                node=UpdateChatNode,
                connections=[],
                description="",
            ),
        ],
    )
