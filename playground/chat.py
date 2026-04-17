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
Playground for the chat example workflow.

Prerequisite: a row in the `chats` table must exist with the ID referenced by
the request example (default: 00000000-0000-0000-0000-000000000001). The
workflow reads and updates this row to maintain message history.
"""

event_path = project_root / "app/workflows/chat/request_examples/message.json"
with open(event_path) as f:
    event = json.load(f)

workflow = WorkflowRegistry.CHAT.value()
output = workflow.run(event)
print(output.model_dump_json(indent=2))
