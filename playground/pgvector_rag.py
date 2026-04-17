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
Playground for the pgvector_rag example workflow.

Prerequisite: a `docs` collection in pgvector with embedded documents to
retrieve. Without documents, the retrieval step returns empty results.
"""

event_path = (
    project_root / "app/workflows/pgvector_rag/request_examples/query.json"
)
with open(event_path) as f:
    event = json.load(f)

workflow = WorkflowRegistry.PGVECTOR_RAG.value()
output = workflow.run(event)
print(output.model_dump_json(indent=2))
