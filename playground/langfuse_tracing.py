import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "app"))
sys.path.append(str(project_root))

load_dotenv(project_root / "app/.env")

import nest_asyncio
from workflows.workflow_registry import WorkflowRegistry

logging.basicConfig(level=logging.INFO)
nest_asyncio.apply()

"""
Playground for the langfuse_tracing example workflow.

Prerequisite: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL
in your environment if you want traces to be sent to Langfuse.
"""

event_path = (
    project_root / "app/workflows/langfuse_tracing/request_examples/violation.json"
)
with open(event_path) as f:
    event = json.load(f)

workflow = WorkflowRegistry.LANGFUSE_TRACING.value()
output = workflow.run(event)
print(output.model_dump_json(indent=2))
