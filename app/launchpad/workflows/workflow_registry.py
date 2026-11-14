from enum import Enum

from launchpad.workflows.examples.decision.workflow import DecisionWorkflow
from launchpad.workflows.examples.streaming.workflow import ExampleStreamingWorkflow
from launchpad.workflows.examples.quickstart.workflow import CustomerCareWorkflow
from launchpad.workflows.examples.langfuse_tracing.workflow import (
    LangfuseTracingWorkflow,
)
from launchpad.workflows.examples.nested_workflow.workflow import (
    NestedWorkflow,
)
from launchpad.workflows.examples.pgvector_rag.workflow import RagExampleWorkflow

from launchpad.workflows.examples.research_workspace.workflow import (
    ResearchImportWorkflow,
    ResearchMeetingWorkflow,
    ResearchNotionWorkflow,
    ResearchWeeklyWorkflow,
    ResearchPdfWorkflow,
    ResearchReadingWorkflow,
    ResearchSearchWorkflow,
    ResearchTranslationWorkflow,
)


class WorkflowRegistry(Enum):
    DECISION = DecisionWorkflow
    STREAMING = ExampleStreamingWorkflow
    QUICKSTART = CustomerCareWorkflow
    LANGFUSE_TRACING = LangfuseTracingWorkflow
    PGVECTOR_RAG = RagExampleWorkflow
    NESTED_WORKFLOW = NestedWorkflow
    RESEARCH_IMPORT = ResearchImportWorkflow
    RESEARCH_READING = ResearchReadingWorkflow
    RESEARCH_PDF = ResearchPdfWorkflow
    RESEARCH_SEARCH = ResearchSearchWorkflow
    RESEARCH_WEEKLY = ResearchWeeklyWorkflow
    RESEARCH_MEETING = ResearchMeetingWorkflow
    RESEARCH_NOTION = ResearchNotionWorkflow
    RESEARCH_TRANSLATE = ResearchTranslationWorkflow
