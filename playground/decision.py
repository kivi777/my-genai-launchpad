import json
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

from launchpad.workflows.workflow_registry import WorkflowRegistry  # noqa: E402

event_path = (
    project_root / "app/launchpad/workflows/decision/request_examples/ticket.json"
)
event = json.loads(event_path.read_text())
output = WorkflowRegistry.DECISION.value().run(event)
print(output.model_dump_json(indent=2))
