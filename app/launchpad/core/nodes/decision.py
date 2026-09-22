from abc import abstractmethod

from pydantic import BaseModel
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score, SystemOneResponse

from launchpad.core.nodes.base import Node


class DecisionConfig(BaseModel):
    model_name: str = "jev-1.13.0"
    questions: dict[str, Choice | Score | Noul]


class DecisionNode(Node):
    """Subclass with typed OutputType and process(), as with AgentNode."""

    @abstractmethod
    def get_decision_config(self) -> DecisionConfig:
        pass

    async def decide(self, state: BaseModel | str) -> SystemOneResponse:
        """Evaluate state, keeping Jev's typed answers and probabilities intact."""
        config = self.get_decision_config()
        async with AsyncTypeSafeClient(model=config.model_name) as client:
            return await client.system_one(
                state=state.model_dump(mode="json")
                if isinstance(state, BaseModel)
                else state,
                questions=config.questions,
            )
