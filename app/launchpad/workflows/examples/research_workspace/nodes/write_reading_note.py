import re
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext
from launchpad.services.prompt_loader import PromptManager

from .. import config
from ..external_tools import query_external_research_tool
from ..models import deepseek_model
from ..schema import (
    CitedPassage,
    Paper,
    PaperChunk,
    PaperId,
    ReadingNote,
    ReadingResult,
)
from .retrieve_papers import RetrievePapersNode

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
UNDECODED_FORMULA = re.compile(r"<!--\s*formula-not-decoded\s*-->", re.IGNORECASE)
INLINE_CITATION = re.compile(r"[ \t]*[\[［【]C\d+(?:[、,，;；]\s*C\d+)*[\]］】]")


class ReadingContext(BaseModel):
    papers: dict[str, Paper]
    passages: dict[str, PaperChunk]


def list_paper_assets(ctx: RunContext[ReadingContext], paper_id: PaperId) -> list[dict]:
    """Look up the registered code repositories and datasets for a retrieved paper."""
    paper = ctx.deps.papers.get(paper_id)
    if paper is None:
        raise ModelRetry("Use a paper ID from the supplied evidence.")
    return [asset.model_dump(mode="json") for asset in paper.assets]


class WriteReadingNoteNode(Node):
    def build_agent(self, *, trace: bool = False) -> Agent[ReadingContext, ReadingNote]:
        tools = [list_paper_assets]
        if (
            config.EXTERNAL_MCP_URL
            and config.EXTERNAL_MCP_TOOL
            and not config.USE_SAMPLE_MODELS
        ):
            tools.append(query_external_research_tool)
        agent = Agent(
            FunctionModel(self.demo_response)
            if config.USE_SAMPLE_MODELS
            else deepseek_model(config.CHAT_MODEL),
            instructions=PromptManager.get_prompt("reading_note", prompts_dir=PROMPTS),
            deps_type=ReadingContext,
            output_type=ReadingNote,
            tools=tools,
            model_settings={
                "timeout": 45,
                "max_tokens": 900,
                "extra_body": {"thinking": {"type": "disabled"}},
            },
        )
        agent.instrument = trace
        return agent

    def demo_response(
        self, _messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        hit = self.get_output(RetrievePapersNode).hits[0]
        excerpt = hit.chunk.text if hit.chunk else hit.paper.abstract
        excerpt = UNDECODED_FORMULA.sub("", excerpt).strip()
        if len(excerpt) > 200:
            excerpt = f"{excerpt[:197].rstrip()}…"
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "answer": excerpt or hit.paper.title,
                        "cited_paper_ids": [hit.paper.id],
                        "cited_chunk_ids": ["C1"] if hit.chunk else [],
                    },
                )
            ]
        )

    async def process(self, task_context: TaskContext) -> TaskContext:
        hits = self.get_output(RetrievePapersNode).hits
        papers = {hit.paper.id: hit.paper for hit in hits}
        if not papers:
            self.save_output(
                ReadingResult(
                    note=ReadingNote(
                        answer="当前资料库没有检索到相关文献。",
                        cited_paper_ids=[],
                    ),
                    sources=[],
                )
            )
            return task_context

        passages = {f"C{i}": hit.chunk for i, hit in enumerate(hits, 1) if hit.chunk}
        passage_papers = {f"C{i}": hit.paper.id for i, hit in enumerate(hits, 1)}

        agent = self.build_agent(trace=task_context.trace_id is not None)

        @agent.output_validator
        def check_citations(
            ctx: RunContext[ReadingContext], note: ReadingNote
        ) -> ReadingNote:
            if set(note.cited_paper_ids) - ctx.deps.papers.keys():
                raise ModelRetry("Only cite IDs present in the retrieved evidence.")
            if set(note.cited_chunk_ids) - ctx.deps.passages.keys():
                raise ModelRetry(
                    "Only cite passage IDs present in the retrieved evidence."
                )
            if any(
                passage_papers[cid] not in note.cited_paper_ids
                for cid in note.cited_chunk_ids
            ):
                raise ModelRetry("Include the source paper ID for each cited passage.")
            answer = INLINE_CITATION.sub("", UNDECODED_FORMULA.sub("", note.answer))
            return note.model_copy(update={"answer": answer.strip()})

        evidence = []
        for i, hit in enumerate(hits, 1):
            passage = None
            if hit.chunk:
                passage = hit.chunk.model_dump(mode="json", exclude={"regions"})
                passage["text"] = UNDECODED_FORMULA.sub("", hit.chunk.text)
            evidence.append(
                {
                    "paper_id": hit.paper.id,
                    "title": hit.paper.title,
                    "source_kind": hit.paper.source_kind,
                    "passage_id": f"C{i}" if passage else None,
                    "passage": passage,
                }
            )
        prompt = PromptManager.get_prompt(
            "reading_request",
            prompts_dir=PROMPTS,
            query=task_context.event.query,
            previous_turns=[
                turn.model_dump() for turn in task_context.event.previous_turns
            ],
            evidence=evidence,
        )
        result = await agent.run(
            prompt,
            deps=ReadingContext(papers=papers, passages=passages),
            usage_limits=UsageLimits(request_limit=8, tool_calls_limit=12),
        )
        self.save_output(
            ReadingResult(
                note=result.output,
                passages={
                    cid: CitedPassage(
                        paper_id=passage_papers[cid],
                        locator=hits[int(cid[1:]) - 1].locator,
                        **passages[cid].model_dump(),
                    )
                    for cid in result.output.cited_chunk_ids
                },
                sources=[
                    papers[paper_id]
                    for paper_id in dict.fromkeys(result.output.cited_paper_ids)
                ],
            )
        )
        return task_context
