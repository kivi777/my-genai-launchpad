from enum import Enum

from workflows.streaming.workflow import ExampleStreamingWorkflow
from workflows.quickstart.workflow import CustomerCareWorkflow
from workflows.chat.workflow import ChatExampleWorkflow
from workflows.langfuse_tracing.workflow import LangfuseTracingWorkflow
from workflows.pgvector_rag.workflow import RagExampleWorkflow


class WorkflowRegistry(Enum):
    STREAMING = ExampleStreamingWorkflow
    QUICKSTART = CustomerCareWorkflow
    CHAT = ChatExampleWorkflow
    LANGFUSE_TRACING = LangfuseTracingWorkflow
    PGVECTOR_RAG = RagExampleWorkflow
