from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

from ..library import search_papers
from ..schema import SearchEvent, SearchHit
from .plan_retrieval import PlanRetrievalNode


class RetrievePapersNode(Node):
    class OutputType(Node.OutputType):
        hits: list[SearchHit]

    async def process(self, task_context: TaskContext) -> TaskContext:
        event: SearchEvent = task_context.event
        plan = self.get_output(PlanRetrievalNode)
        retrieval = event.model_copy(
            update={"query": plan.semantic_query, "keywords": plan.keywords}
        )
        hits = await search_papers(retrieval, original_query=event.query)
        for hit in hits:
            if hit.paper.pdf_run_id and hit.chunk and hit.chunk.pages:
                hit.locator = (
                    f"/research/pdf/{hit.paper.pdf_run_id}#page={hit.chunk.pages[0]}"
                )
        self.save_output(self.OutputType(hits=hits))
        return task_context
