from typing import Any

from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python

from core.nodes.agent import AgentNode, AgentConfig, ModelProvider
from core.task import TaskContext
from workflows.chat.schema import ChatCompletionEventSchema
from workflows.chat.nodes.prepare_chat_node import PrepareChatNode


class ChatCompletionNode(AgentNode):
    class OutputType(AgentNode.OutputType):
        model_output: str
        history: Any

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt="You are a tutor teaching people that are new to programming. Ask questions that help the user get a better understanding of the current subject they are struggling with.",
            output_type=str,
            deps_type=None,
            model_provider=ModelProvider.OPENAI,
            model_name="gpt-5.4-mini",
        )

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: ChatCompletionEventSchema = task_context.event
        prepare_chat_node: PrepareChatNode.OutputType = self.get_output(PrepareChatNode)

        pydantic_message_history = prepare_chat_node.pydantic_message_history

        message_history = []
        if pydantic_message_history:
            message_history = ModelMessagesTypeAdapter.validate_python(
                pydantic_message_history
            )

        result = await self.agent.run(
            user_prompt=event.content, message_history=message_history
        )

        # Store the PydanticAI message history
        history = to_jsonable_python(result.all_messages())

        output = self.OutputType(model_output=result.output, history=history)
        self.save_output(output)

        return task_context
