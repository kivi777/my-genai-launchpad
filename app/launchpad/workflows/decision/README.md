# Jev decision node

[Jev](https://docs.typesafe.ai/concepts/system-one) is TypeSafe's System One
model for structured decisions. Give it state, such as a support ticket, and
questions with defined answer spaces. It returns typed answers and probabilities
that application code can act on.

A calibrated decision model aims to make its probabilities reflect observed
outcomes. For example, across comparable predictions assigned an 80% probability,
roughly 80% should be correct. TypeSafe trains System One models toward this goal;
calibration is a property measured across predictions, not a guarantee for any
single decision. Validate it on representative data for your application.

This fits naturally into Launchpad: a workflow already passes state between nodes
and uses routers to choose what happens next. A decision node can classify that
state, save a typed result, and let a router select the next node or send an
uncertain case for review. An `AgentNode` can then handle tasks such as writing a
reply. Pydantic validates the output's structure; calibration concerns the quality
of the model's probabilities.

## How the node works

`DecisionNode` and `AgentNode` share one base, `PydanticAINode`. Both build a
PydanticAI `Agent`; `DecisionNode` runs it on
[PydanticAI's TypeSafe model](https://pydantic.dev/docs/ai/models/typesafe/).
Implement `get_agent_config()` returning a `DecisionConfig`, define a Pydantic
`OutputType`, and implement `process()` using `self.agent.run(...)` and
`save_output()`.

Jev does not generate text. The prompt is the text being judged, and the
fields of `output_type` are the questions. The field type sets the kind of
question:

- `Enum` or `Literal`: pick one option. Describe options with
  `UseEnumMemberDocstrings` and a docstring under each member.
- `bool`: yes or no.
- `float` with `ge=0, le=1`: the probability itself.
- `IntEnum` rubric with a docstring per level: a score.

Put the question in the field `description`. Read the confidence per field
from `result.response.provider_details["confidence"]`. See the
[PydanticAI TypeSafe docs](https://pydantic.dev/docs/ai/models/typesafe/) for
all supported types, thresholds, tools, and limits.

## What this example does

The registered `DECISION` workflow contains one node, `DecideTeamNode`:

1. Receive a `TicketEvent` containing a support message.
2. Ask Jev which team should handle it: `billing`, `technical`, or `other`.
3. Read the selected `Team` and Jev's confidence for that field, constrained
   to 0–1.
4. Save that output in `TaskContext.nodes["DecideTeamNode"]`.

The sample ticket asks for a refund after a duplicate charge. The playground
prints the resulting task context as JSON, including the selected team and
confidence. The workflow ends after saving the decision; dispatching a ticket
would be a subsequent workflow step.

Downstream nodes can read the result with `self.get_output(DecideTeamNode)`.
A router could branch on `output.team` or use a validated confidence threshold
for review. Jev's Choice confidence summarizes how concentrated the probability
distribution is; it is not the selected option's probability. See
[Choice responses](https://docs.typesafe.ai/primitives/choice#response-structure).

## Run the example

From the repository root:

1. Install dependencies with `uv sync`.
2. Set `TYPESAFE_API_KEY` in the root `.env`:

   ```dotenv
   TYPESAFE_API_KEY=your-api-key
   ```

3. Run the playground:

   ```bash
   uv run python playground/decision.py
   ```

Edit `request_examples/ticket.json` to try a different message. The playground
loads that file and runs the workflow locally without API or Celery services.

The model defaults to `jev-1.13.0`; override `model_name` in `DecisionConfig` to
change it. Tune thresholds with `model_settings=TypeSafeModelSettings(...)`.
PydanticAI reads `TYPESAFE_API_KEY` from the environment.
For Docker, set the key in `docker/.env` and rebuild the API and worker services.
