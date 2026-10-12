"""Validation report: typed violations."""

from __future__ import annotations

from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field


class Check(str, Enum):
    REFERENCES = "references"
    COMPLETENESS = "completeness"
    CAPABILITY = "capability"
    ENERGY = "energy"
    ROUTE = "route"
    TEMPORAL = "temporal"
    CONFLICT = "conflict"


class ViolationCode(str, Enum):
    # 1. reference integrity (hallucinations)
    UNKNOWN_MACHINE = "UNKNOWN_MACHINE"
    UNKNOWN_TASK = "UNKNOWN_TASK"
    UNKNOWN_ZONE = "UNKNOWN_ZONE"
    # 2. completeness
    TASK_UNASSIGNED = "TASK_UNASSIGNED"
    TASK_DUPLICATED = "TASK_DUPLICATED"
    # 3. capability and payload
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    PAYLOAD_EXCEEDED = "PAYLOAD_EXCEEDED"
    # 4. energy
    ENERGY_DEPLETED = "ENERGY_DEPLETED"
    RESERVE_VIOLATED = "RESERVE_VIOLATED"
    INVALID_CHARGING_STOP = "INVALID_CHARGING_STOP"
    # 5. route
    EDGE_MISSING = "EDGE_MISSING"
    NO_GO_ZONE = "NO_GO_ZONE"
    NO_GO_EDGE = "NO_GO_EDGE"
    ROUTE_START_MISMATCH = "ROUTE_START_MISMATCH"
    ROUTE_END_MISMATCH = "ROUTE_END_MISMATCH"
    # 6. temporal
    PRECEDENCE_VIOLATED = "PRECEDENCE_VIOLATED"
    TIME_WINDOW_VIOLATED = "TIME_WINDOW_VIOLATED"
    MACHINE_OVERLAP = "MACHINE_OVERLAP"
    TRAVEL_TIME_INFEASIBLE = "TRAVEL_TIME_INFEASIBLE"
    DURATION_TOO_SHORT = "DURATION_TOO_SHORT"
    # v0.2 (experimental, opt-in)
    SINGLE_LANE_CONFLICT = "SINGLE_LANE_CONFLICT"

    @property
    def check(self) -> Check:
        return _CODE_TO_CHECK[self]


_CODE_TO_CHECK: dict[ViolationCode, Check] = {
    **dict.fromkeys(
        (ViolationCode.UNKNOWN_MACHINE, ViolationCode.UNKNOWN_TASK, ViolationCode.UNKNOWN_ZONE),
        Check.REFERENCES,
    ),
    **dict.fromkeys(
        (ViolationCode.TASK_UNASSIGNED, ViolationCode.TASK_DUPLICATED), Check.COMPLETENESS
    ),
    **dict.fromkeys(
        (ViolationCode.CAPABILITY_MISSING, ViolationCode.PAYLOAD_EXCEEDED), Check.CAPABILITY
    ),
    **dict.fromkeys(
        (
            ViolationCode.ENERGY_DEPLETED,
            ViolationCode.RESERVE_VIOLATED,
            ViolationCode.INVALID_CHARGING_STOP,
        ),
        Check.ENERGY,
    ),
    **dict.fromkeys(
        (
            ViolationCode.EDGE_MISSING,
            ViolationCode.NO_GO_ZONE,
            ViolationCode.NO_GO_EDGE,
            ViolationCode.ROUTE_START_MISMATCH,
            ViolationCode.ROUTE_END_MISMATCH,
        ),
        Check.ROUTE,
    ),
    **dict.fromkeys(
        (
            ViolationCode.PRECEDENCE_VIOLATED,
            ViolationCode.TIME_WINDOW_VIOLATED,
            ViolationCode.MACHINE_OVERLAP,
            ViolationCode.TRAVEL_TIME_INFEASIBLE,
            ViolationCode.DURATION_TOO_SHORT,
        ),
        Check.TEMPORAL,
    ),
    ViolationCode.SINGLE_LANE_CONFLICT: Check.CONFLICT,
}


class Violation(BaseModel):
    code: ViolationCode
    message: str
    machine_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    zone_ids: list[str] = Field(default_factory=list)

    @property
    def check(self) -> Check:
        return self.code.check

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


class ValidationReport(BaseModel):
    scenario_id: str
    valid: bool
    violations: list[Violation] = Field(default_factory=list)
    makespan: float | None = None

    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(v.code.value for v in self.violations).items()))

    @property
    def has_hallucination(self) -> bool:
        return any(v.check is Check.REFERENCES for v in self.violations)

    def summary(self) -> str:
        head = f"Scenario {self.scenario_id}: {'PASS' if self.valid else 'FAIL'}"
        if self.valid:
            return f"{head} (makespan {self.makespan:g})"
        lines = [f"{head} ({len(self.violations)} violation(s))"]
        lines += [f"  - {v}" for v in self.violations]
        return "\n".join(lines)
