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
Playground for the pgvector_rag example workflow.

Prerequisite: a `docs` collection in pgvector with embedded documents to
retrieve. Without documents, the retrieval step returns empty results.
"""

event_path = (
    project_root / "app/launchpad/workflows/examples/pgvector_rag/request_examples/query.json"
)
with open(event_path) as f:
    event = json.load(f)

workflow = WorkflowRegistry.PGVECTOR_RAG.value()

# Run in a worker thread with its own event loop so this script works both as
# `python pgvector_rag.py` and inside a Jupyter Interactive Window (where the
# kernel already owns the main loop).
with ThreadPoolExecutor(max_workers=1) as pool:
    output = pool.submit(workflow.run, event).result()

print(output.model_dump_json(indent=2))
