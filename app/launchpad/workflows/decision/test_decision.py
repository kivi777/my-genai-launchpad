import json
import unittest
from unittest.mock import patch

import httpx2
from pydantic import ValidationError
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeAPIResponseValidationError

from launchpad.core.task import TaskContext
from launchpad.workflows.decision.nodes.decide_team_node import DecideTeamNode, Team
from launchpad.workflows.decision.schema import TicketEvent
from launchpad.workflows.workflow_registry import WorkflowRegistry


class DecisionWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.answer = {
            "type": "choice",
            "choice": "billing",
            "confidence": 0.9,
            "probabilities": {"billing": 0.9, "technical": 0.05, "other": 0.05},
        }
        self.requests = []
        self.http_client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(self.respond)
        )
        self.client = AsyncTypeSafeClient(
            api_key="offline-test-key",
            model="jev-1.13.0",
            http_client=self.http_client,
        )
        self.client_patch = patch(
            "launchpad.core.nodes.decision.AsyncTypeSafeClient",
            return_value=self.client,
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.addAsyncCleanup(self.client.aclose)

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "usage": {"input_tokens": 20},
                "answers": {"team": self.answer},
            },
        )

    async def test_registered_workflow_saves_typed_decision(self) -> None:
        context = await WorkflowRegistry.DECISION.value().run_async(
            {"message": "I was charged twice."}
        )
        output = context.nodes["DecideTeamNode"]
        self.assertIsInstance(output, DecideTeamNode.OutputType)
        self.assertIs(output.team, Team.BILLING)
        self.assertEqual(output.confidence, 0.9)
        self.assertEqual(self.requests[0]["state"], {"message": "I was charged twice."})
        self.assertEqual(self.requests[0]["model"], "jev-1.13.0")
        self.assertEqual(
            set(self.requests[0]["questions"]["team"]["criteria"]),
            {"billing", "technical", "other"},
        )
        self.assertTrue(self.http_client.is_closed)

    async def test_unknown_team_is_not_saved(self) -> None:
        self.answer["choice"] = "sales"
        context = TaskContext(event=TicketEvent(message="Help"))
        with self.assertRaises(ValueError):
            await DecideTeamNode(context).process(context)
        self.assertEqual(context.nodes, {})
        self.assertTrue(self.http_client.is_closed)

    async def test_invalid_confidence_is_not_saved(self) -> None:
        self.answer["confidence"] = 1.5
        context = TaskContext(event=TicketEvent(message="Help"))
        with self.assertRaises(ValidationError):
            await DecideTeamNode(context).process(context)
        self.assertEqual(context.nodes, {})
        self.assertTrue(self.http_client.is_closed)

    async def test_malformed_response_closes_client_without_saving(self) -> None:
        del self.answer["choice"]
        context = TaskContext(event=TicketEvent(message="Help"))
        with self.assertRaises(TypeSafeAPIResponseValidationError):
            await DecideTeamNode(context).process(context)
        self.assertEqual(context.nodes, {})
        self.assertTrue(self.http_client.is_closed)
