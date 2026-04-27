import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent

load_dotenv(project_root / ".env")

from launchpad.workflows.workflow_registry import WorkflowRegistry

logging.basicConfig(level=logging.INFO)

"""
Playground for the langfuse_tracing example workflow.

Prerequisite: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL
in your environment if you want traces to be sent to Langfuse.
"""

event_path = (
    project_root / "app/launchpad/workflows/examples/langfuse_tracing/request_examples/violation.json"
)
with open(event_path) as f:
    event = json.load(f)

workflow = WorkflowRegistry.LANGFUSE_TRACING.value()

# Run in a worker thread with its own event loop so this script works both as
# `python langfuse_tracing.py` and inside a Jupyter Interactive Window (where
# the kernel already owns the main loop).
with ThreadPoolExecutor(max_workers=1) as pool:
    output = pool.submit(workflow.run, event).result()

print(output.model_dump_json(indent=2))
