# Jev decision node

Minimal integration of the [AI cookbook Jev example](https://github.com/daveebbelaar/ai-cookbook/tree/main/models/jev) into Launchpad.

`DecisionNode` mirrors `AgentNode`: implement `get_decision_config()`, define a
Pydantic `OutputType`, and implement `process()` using `save_output()`.
Call `await self.decide(state)` with text or a Pydantic model. The result is the
SDK's Pydantic `SystemOneResponse`, preserving answers, probabilities, and usage.
The async client closes after each call, including on failure.

`DecisionConfig` accepts Jev's native `Choice`, `Score`, and `Noul` questions.
Read `response.choices[name]`, `response.scores[name]`, or `response.nouls[name]`
and explicitly map the needed fields into your node's `OutputType`.
`DecideTeamNode` demonstrates a choice validated against a `Team` enum and a
confidence constrained to 0–1. Downstream nodes use the usual
`self.get_output(DecideTeamNode)` pattern. A router can branch on `output.team`.
This workflow returns the decision; it does not dispatch tickets.

## Run

1. Run `uv sync`.
2. Set `TYPESAFE_API_KEY` in the root `.env`.
3. Run `uv run python playground/decision.py`.

For Docker, set the key in `docker/.env` and rebuild the API and worker.
The registered workflow name is `DECISION`. The model defaults to `jev-1.13.0`;
override `model_name` in `DecisionConfig` to change it. Credentials are resolved
by the SDK from the environment, not embedded in workflow configuration.

Typed output validates structure, not decision accuracy. Jev probabilities are
not a correctness guarantee; evaluate decisions on representative inputs.
See the [official SDK documentation](https://docs.typesafe.ai/sdk/python).

## Offline checks

`uv run python -m unittest discover -s app/launchpad/workflows/decision -p 'test_*.py'`
