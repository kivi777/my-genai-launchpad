import json
from pathlib import Path

from pydantic_ai import Agent, UsageLimits

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext
from launchpad.services.prompt_loader import PromptManager

from .. import config
from ..models import deepseek_model
from ..schema import ReadingPlan, SearchEvent

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


class PlanRetrievalNode(Node):
    def build_agent(self, *, trace: bool = False) -> Agent[None, ReadingPlan]:
        agent = Agent(
            deepseek_model(config.INTENT_MODEL),
            instructions=PromptManager.get_prompt(
                "plan_retrieval", prompts_dir=PROMPTS
            ),
            output_type=ReadingPlan,
            model_settings={
                "timeout": 30,
                "extra_body": {"thinking": {"type": "disabled"}},
            },
        )
        agent.instrument = trace
        return agent

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: SearchEvent = task_context.event
        if config.USE_SAMPLE_MODELS:
            question = event.query.casefold()
            asset_kinds = []
            if any(term in question for term in ("代码", "code", "github", "repo")):
                asset_kinds.append("code")
            if any(term in question for term in ("数据集", "dataset")):
                asset_kinds.append("dataset")
            plan = ReadingPlan(
                semantic_query=event.query,
                keywords=event.keywords,
                compare=any(
                    term in question
                    for term in ("对比", "比较", "分别", "compare", "versus")
                ),
                asset_kinds=asset_kinds,
            )
        else:
            prompt = event.query
            if event.previous_turns:
                prompt = json.dumps(
                    {
                        "question": event.query,
                        "previous_turns": [
                            turn.model_dump() for turn in event.previous_turns
                        ],
                    },
                    ensure_ascii=False,
                )
            result = await self.build_agent(
                trace=task_context.trace_id is not None
            ).run(prompt, usage_limits=UsageLimits(request_limit=3))
            plan = result.output
        if event.keywords and event.keywords.strip():
            plan = plan.model_copy(update={"keywords": event.keywords})
        self.save_output(plan)
        return task_context
