from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai.models.typesafe import (
    TypeSafeModel,
    TypeSafeModelName,
    TypeSafeModelSettings,
)

from launchpad.core.nodes.pydantic_ai_node import PydanticAIConfig, PydanticAINode


@dataclass(kw_only=True)
class DecisionConfig(PydanticAIConfig):
    # Pinned so tuned confidence thresholds keep meaning the same thing.
    model_name: TypeSafeModelName = "jev-1.13.0"
    model_settings: TypeSafeModelSettings | None = None


class DecisionNode(PydanticAINode, ABC):
    """Typed decision node backed by TypeSafe's Jev.

    Jev does not generate text. Each field of `output_type` is a question, and
    each answer comes with a confidence in
    `result.response.provider_details["confidence"]`.
    """

    @abstractmethod
    def get_agent_config(self) -> DecisionConfig:
        pass

    def build_model(self, config: DecisionConfig) -> Model:
        return TypeSafeModel(config.model_name)
