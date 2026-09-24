from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic_ai.models.typesafe import TypeSafeModelName

from launchpad.core.nodes.agent import AgentConfig, AgentNode, ModelProvider


@dataclass
class DecisionConfig(AgentConfig):
    model_provider: ModelProvider = ModelProvider.TYPESAFE
    # Pinned so tuned confidence thresholds keep meaning the same thing.
    model_name: TypeSafeModelName = "jev-1.13.0"


class DecisionNode(AgentNode, ABC):
    """AgentNode on TypeSafe's Jev: typed decisions, no text generation.

    Each field of `output_type` is a question. The confidence per field is in
    `result.response.provider_details["confidence"]`.
    """

    @abstractmethod
    def get_agent_config(self) -> DecisionConfig:
        pass
