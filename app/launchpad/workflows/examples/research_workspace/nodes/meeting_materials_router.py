from launchpad.core.nodes.base import Node
from launchpad.core.nodes.router import BaseRouter
from launchpad.core.task import TaskContext

from .plan_meeting import PlanMeetingNode
from .plan_retrieval import PlanRetrievalNode
from .read_meeting_notes import ReadMeetingNotesNode


class MeetingMaterialsRouter(BaseRouter):
    def route(self, task_context: TaskContext) -> Node:
        if task_context.nodes[ReadMeetingNotesNode.__name__].notes:
            return PlanMeetingNode()
        return PlanRetrievalNode()
