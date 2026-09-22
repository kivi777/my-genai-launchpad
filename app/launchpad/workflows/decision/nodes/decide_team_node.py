from enum import StrEnum

from pydantic import Field
from typesafe_sdk import Choice

from launchpad.core.nodes.decision import DecisionConfig, DecisionNode
from launchpad.core.task import TaskContext
from launchpad.workflows.decision.schema import TicketEvent


class Team(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    OTHER = "other"


class DecideTeamNode(DecisionNode):
    class OutputType(DecisionNode.OutputType):
        team: Team
        confidence: float = Field(ge=0, le=1)

    def get_decision_config(self) -> DecisionConfig:
        return DecisionConfig(
            questions={
                "team": Choice(
                    instructions="Which team should handle this support ticket?",
                    criteria={
                        Team.BILLING: "Payments, charges, or refunds.",
                        Team.TECHNICAL: "Errors, bugs, or login failures.",
                        Team.OTHER: "Anything else.",
                    },
                ),
            },
        )

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: TicketEvent = task_context.event
        response = await self.decide(event)
        answer = response.choices["team"]
        self.save_output(
            self.OutputType(team=Team(answer.choice), confidence=answer.confidence)
        )
        return task_context
