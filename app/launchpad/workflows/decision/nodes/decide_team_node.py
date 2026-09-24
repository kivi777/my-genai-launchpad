from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai import UseEnumMemberDocstrings

from launchpad.core.nodes.decision import DecisionConfig, DecisionNode
from launchpad.core.task import TaskContext
from launchpad.workflows.decision.schema import TicketEvent


class Team(UseEnumMemberDocstrings, StrEnum):
    BILLING = "billing"
    """Payments, charges, or refunds."""
    TECHNICAL = "technical"
    """Errors, bugs, or login failures."""
    OTHER = "other"
    """Anything else."""


class TeamQuestion(BaseModel):
    """Route a support ticket to the team that should handle it."""

    team: Team = Field(description="Which team should handle this support ticket?")


class DecideTeamNode(DecisionNode):
    class OutputType(DecisionNode.OutputType):
        team: Team
        confidence: float = Field(ge=0, le=1)

    def get_agent_config(self) -> DecisionConfig:
        return DecisionConfig(output_type=TeamQuestion)

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: TicketEvent = task_context.event
        result = await self.agent.run(event.message)
        confidence = result.response.provider_details["confidence"]["team"]
        self.save_output(
            self.OutputType(team=result.output.team, confidence=confidence)
        )
        return task_context
