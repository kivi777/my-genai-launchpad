from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, AgentRetries
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext


@dataclass(kw_only=True)
class PydanticAIConfig:
    """Agent options shared by every PydanticAI-backed node."""

    model_name: str
    output_type: Any = str
    instructions: str | None = None
    deps_type: type[Any] | None = None
    name: str | None = None
    model_settings: ModelSettings | None = None
    retries: int | AgentRetries = 1
    tools: list = field(default_factory=list)
    # Native tools, thinking, web search, etc. See pydantic_ai.capabilities.
    capabilities: list[AgentCapability] = field(default_factory=list)
    instrument: bool = True


class PydanticAINode(Node, ABC):
    """Base for nodes that run a PydanticAI agent.

    Subclasses pick the model in `build_model()`; users implement
    `get_agent_config()` and `process()`.
    """

    class DepsType(BaseModel):
        pass

    class OutputType(BaseModel):
        pass

    def __init__(self, task_context: TaskContext = None):
        super().__init__(task_context=task_context)

        config = self.get_agent_config()
        self.agent = Agent(
            model=self.build_model(config),
            output_type=config.output_type,
            instructions=config.instructions,
            deps_type=config.deps_type,
            name=config.name,
            model_settings=config.model_settings,
            retries=config.retries,
            tools=config.tools,
            capabilities=config.capabilities,
        )
        self.agent.instrument = config.instrument
        Agent.instrument_all()

    @abstractmethod
    def get_agent_config(self) -> PydanticAIConfig:
        pass

    @abstractmethod
    def build_model(self, config: PydanticAIConfig) -> Model:
        pass

    @abstractmethod
    async def process(self, task_context: TaskContext) -> TaskContext:
        pass
