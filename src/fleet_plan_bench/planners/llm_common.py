"""Provider-neutral pieces shared by the LLM planner adapters: prompt, output schema,
response parsing. The LLM only proposes; the deterministic validator judges."""

from __future__ import annotations

import json
import re
from typing import Any

from fleet_plan_bench.io import parse_planner_output
from fleet_plan_bench.planners.base import RepairFeedback
from fleet_plan_bench.schemas import Infeasible, Plan, Scenario

SYSTEM_PROMPT = """\
You are a fleet planner for heterogeneous field vehicles. Given a scenario (fleet, site
graph, mission), produce a plan that a strict deterministic validator will accept, or
declare the mission infeasible if no valid plan exists.

Rules the validator enforces:
- Use only machine, task and zone ids that appear in the scenario.
- Assign every task exactly once to a machine that has its required_capability and
  whose payload_capacity >= the task's payload_demand.
- Each machine executes its assignments in order of start time. The route of an
  assignment lists zones from where the machine is (its start_zone for its first task,
  otherwise the zone of its previous task) to the task zone, inclusive. A one-element
  route means it is already there.
- Consecutive route zones must be joined by an edge (edges are undirected). Never enter a
  zone with no_go true or use an edge with no_go true.
- Travel time on an edge = distance / speed. The machine departs when its previous task
  ends (or at available_from), so start >= departure + travel time + charging time.
- end - start >= duration. Tasks of one machine must not overlap.
- A task starts only after every task in its precedence list has ended.
- If a task has a time_window, start >= earliest_start and end <= latest_end.
- Energy: machines start with initial_energy (or a full battery if null). Each edge costs
  distance * energy_per_distance. After every edge, energy must stay >= {reserve:.0%} of
  battery_capacity. A charging stop {{"zone": Z}} charges to full at zone Z, which must be
  a charging station on the route; it takes (capacity - energy) / charge_rate time.

Output JSON only, with this shape:
{{"kind": "plan", "reason": "", "assignments": [{{"machine": ..., "task": ..., "route": [...],
  "start": number, "end": number, "charging_stops": [{{"zone": ...}}]}}]}}
or, if the mission cannot be done:
{{"kind": "infeasible", "reason": "<which constraint makes it impossible>", "assignments": []}}
"""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["plan", "infeasible"]},
        "reason": {"type": "string"},
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "machine": {"type": "string"},
                    "task": {"type": "string"},
                    "route": {"type": "array", "items": {"type": "string"}},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "charging_stops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"zone": {"type": "string"}},
                            "required": ["zone"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["machine", "task", "route", "start", "end", "charging_stops"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["kind", "reason", "assignments"],
    "additionalProperties": False,
}


def scenario_prompt(scenario: Scenario) -> str:
    """Scenario JSON for the model, with ground truth and perturbation removed."""
    data = scenario.model_dump(
        mode="json", exclude={"ground_truth", "perturbation"}, exclude_none=False
    )
    return json.dumps(data, indent=1)


def feedback_prompt(feedback: RepairFeedback) -> str:
    lines = [
        f"Repair attempt {feedback.attempt}. The validator rejected your previous plan:",
        feedback.previous.model_dump_json(exclude_none=True),
        "Violations:",
        *(f"- {v.code.value}: {v.message}" for v in feedback.violations),
        "Return a corrected plan (or declare infeasibility if no valid plan exists).",
    ]
    return "\n".join(lines)


def extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating a fenced code block or prose around it."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{"):
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j > i:
            text = text[i : j + 1]
    return json.loads(text)


def to_planner_output(data: Any, planner: str) -> Plan | Infeasible:
    if isinstance(data, dict) and data.get("kind") == "infeasible":
        return Infeasible(reason=str(data.get("reason") or "unspecified"), planner=planner)
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != "reason"}
        data["planner"] = planner
    return parse_planner_output(data)


class LLMOutputError(RuntimeError):
    """The model's response was not a parseable plan. Benchmarks score it SCHEMA_INVALID."""

    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw
