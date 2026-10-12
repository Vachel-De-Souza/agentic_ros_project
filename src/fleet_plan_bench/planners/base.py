"""Planner interface. Any object with a matching ``plan`` method is a planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from fleet_plan_bench.schemas import Infeasible, Plan, Scenario, Violation


@dataclass
class RepairFeedback:
    """Passed to a planner on a repair attempt: its previous plan and what was wrong."""

    attempt: int
    previous: Plan
    violations: list[Violation]


@dataclass
class Usage:
    """Optional cost accounting a planner may expose as ``last_usage``."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_s: float | None = None
    extra: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Planner(Protocol):
    name: str

    def plan(
        self, scenario: Scenario, feedback: RepairFeedback | None = None
    ) -> Plan | Infeasible: ...
