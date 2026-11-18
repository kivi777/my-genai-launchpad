from collections.abc import Iterator
from contextlib import contextmanager

from launchpad.core.schema import NodeConfig, WorkflowSchema
from launchpad.core.workflow import Workflow

from .nodes.import_notion import ImportNotionNode
from .nodes.import_papers import ImportPapersNode
from .nodes.import_pdf import ImportPdfNode
from .nodes.meeting_materials_router import MeetingMaterialsRouter
from .nodes.plan_meeting import PlanMeetingNode
from .nodes.plan_retrieval import PlanRetrievalNode
from .nodes.read_experiments import ReadExperimentsNode
from .nodes.read_meeting_notes import ReadMeetingNotesNode
from .nodes.read_weekly_conversations import ReadWeeklyConversationsNode
from .nodes.render_meeting import RenderMeetingNode
from .nodes.retrieve_papers import RetrievePapersNode
from .nodes.translate_passage import TranslatePassageNode
from .nodes.write_reading_note import WriteReadingNoteNode
from .nodes.write_weekly_report import WriteWeeklyReportNode
from .observability import stage
from .schema import (
    ImportEvent,
    MeetingEvent,
    NotionWorkflowEvent,
    PdfImportEvent,
    SearchEvent,
    TranslationEvent,
    WeeklyReportEvent,
)


class ResearchWorkflow(Workflow):
    @contextmanager
    def node_context(self, node_name: str) -> Iterator[None]:
        with stage(node_name), super().node_context(node_name):
            yield


class ResearchImportWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=ImportEvent,
        start=ImportPapersNode,
        nodes=[NodeConfig(node=ImportPapersNode, connections=[])],
    )


class ResearchReadingWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=SearchEvent,
        start=PlanRetrievalNode,
        nodes=[
            NodeConfig(node=PlanRetrievalNode, connections=[RetrievePapersNode]),
            NodeConfig(node=RetrievePapersNode, connections=[WriteReadingNoteNode]),
            NodeConfig(node=WriteReadingNoteNode, connections=[]),
        ],
    )


class ResearchPdfWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=PdfImportEvent,
        start=ImportPdfNode,
        nodes=[NodeConfig(node=ImportPdfNode, connections=[])],
    )


class ResearchSearchWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=SearchEvent,
        start=PlanRetrievalNode,
        nodes=[
            NodeConfig(node=PlanRetrievalNode, connections=[RetrievePapersNode]),
            NodeConfig(node=RetrievePapersNode, connections=[]),
        ],
    )


class ResearchWeeklyWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=WeeklyReportEvent,
        start=ReadWeeklyConversationsNode,
        nodes=[
            NodeConfig(
                node=ReadWeeklyConversationsNode, connections=[WriteWeeklyReportNode]
            ),
            NodeConfig(node=WriteWeeklyReportNode, connections=[]),
        ],
    )


class ResearchMeetingWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=MeetingEvent,
        start=ReadExperimentsNode,
        nodes=[
            NodeConfig(node=ReadExperimentsNode, connections=[ReadMeetingNotesNode]),
            NodeConfig(node=ReadMeetingNotesNode, connections=[MeetingMaterialsRouter]),
            NodeConfig(
                node=MeetingMaterialsRouter,
                connections=[PlanMeetingNode, PlanRetrievalNode],
                is_router=True,
            ),
            NodeConfig(node=PlanRetrievalNode, connections=[RetrievePapersNode]),
            NodeConfig(node=RetrievePapersNode, connections=[PlanMeetingNode]),
            NodeConfig(node=PlanMeetingNode, connections=[RenderMeetingNode]),
            NodeConfig(node=RenderMeetingNode, connections=[]),
        ],
    )


class ResearchNotionWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=NotionWorkflowEvent,
        start=ImportNotionNode,
        nodes=[NodeConfig(node=ImportNotionNode, connections=[])],
    )


class ResearchTranslationWorkflow(ResearchWorkflow):
    workflow_schema = WorkflowSchema(
        event_schema=TranslationEvent,
        start=TranslatePassageNode,
        nodes=[NodeConfig(node=TranslatePassageNode, connections=[])],
    )
