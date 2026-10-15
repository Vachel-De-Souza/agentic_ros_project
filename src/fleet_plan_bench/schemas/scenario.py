"""Scenario schema: fleet + site + mission + ground truth."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fleet_plan_bench.schemas.plan import Plan


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _dupes(ids: Iterable[str]) -> list[str]:
    return sorted(k for k, n in Counter(ids).items() if n > 1)


class Machine(_Strict):
    id: str
    type: str
    capabilities: list[str]
    speed: float = Field(gt=0, description="distance units per time unit")
    payload_capacity: float = Field(ge=0)
    battery_capacity: float = Field(gt=0)
    energy_per_distance: float = Field(ge=0)
    charge_rate: float = Field(gt=0, description="energy units per time unit")
    start_zone: str
    available_from: float = Field(default=0.0, ge=0)
    initial_energy: float | None = Field(
        default=None, ge=0, description="energy at available_from; None means full"
    )

    @property
    def start_energy(self) -> float:
        return self.battery_capacity if self.initial_energy is None else self.initial_energy


class Zone(_Strict):
    id: str
    kind: str = "area"
    no_go: bool = False
    pos: tuple[float, float] | None = Field(
        default=None, description="optional map position (x, y), used only for visualisation"
    )


class Edge(_Strict):
    """Undirected edge between zones ``a`` and ``b``."""

    a: str
    b: str
    distance: float = Field(gt=0)
    no_go: bool = False
    single_lane: bool = False


class Site(_Strict):
    zones: list[Zone]
    edges: list[Edge]
    charging_stations: list[str] = Field(default_factory=list)


class TimeWindow(_Strict):
    earliest_start: float = 0.0
    latest_end: float = float("inf")


class Task(_Strict):
    id: str
    required_capability: str
    zone: str
    duration: float = Field(ge=0)
    payload_demand: float = Field(default=0.0, ge=0)
    precedence: list[str] = Field(
        default_factory=list, description="ids of tasks that must end before this one starts"
    )
    time_window: TimeWindow | None = None


class Mission(_Strict):
    tasks: list[Task]


class GroundTruth(_Strict):
    feasible: bool
    reason: str | None = Field(default=None, description="why the scenario is infeasible")
    reference_plan: Plan | None = None


class MachineState(_Strict):
    zone: str
    available_from: float = Field(ge=0)
    energy: float = Field(ge=0)


class Perturbation(_Strict):
    """A mid-mission event. Applying it yields a replanning scenario.

    For ``machine_failure``: ``machine`` is removed, ``completed_tasks`` are dropped
    (and removed from precedence lists), and surviving machines start from
    ``machine_states``.
    """

    kind: Literal["machine_failure"] = "machine_failure"
    time: float = Field(ge=0)
    machine: str
    completed_tasks: list[str] = Field(default_factory=list)
    machine_states: dict[str, MachineState] = Field(default_factory=dict)
    ground_truth: GroundTruth


class Scenario(_Strict):
    id: str
    tier: Literal["easy", "medium", "hard"]
    domain: str = Field(default="generic", description="e.g. agriculture, construction, mining")
    description: str = ""
    fleet: list[Machine] = Field(min_length=1)
    site: Site
    mission: Mission
    ground_truth: GroundTruth
    perturbation: Perturbation | None = None

    @model_validator(mode="after")
    def _check_integrity(self) -> Scenario:
        errors: list[str] = []
        zone_ids = {z.id for z in self.site.zones}
        task_ids = {t.id for t in self.mission.tasks}
        machine_ids = {m.id for m in self.fleet}
        for label, ids in (
            ("zone", [z.id for z in self.site.zones]),
            ("machine", [m.id for m in self.fleet]),
            ("task", [t.id for t in self.mission.tasks]),
        ):
            if d := _dupes(ids):
                errors.append(f"duplicate {label} ids: {d}")
        for m in self.fleet:
            if m.start_zone not in zone_ids:
                errors.append(f"machine {m.id}: unknown start_zone {m.start_zone}")
        for e in self.site.edges:
            for z in (e.a, e.b):
                if z not in zone_ids:
                    errors.append(f"edge {e.a}-{e.b}: unknown zone {z}")
        for z in self.site.charging_stations:
            if z not in zone_ids:
                errors.append(f"unknown charging station zone {z}")
        for t in self.mission.tasks:
            if t.zone not in zone_ids:
                errors.append(f"task {t.id}: unknown zone {t.zone}")
            for p in t.precedence:
                if p not in task_ids:
                    errors.append(f"task {t.id}: unknown predecessor {p}")
        if self.perturbation is not None:
            pt = self.perturbation
            if pt.machine not in machine_ids:
                errors.append(f"perturbation: unknown machine {pt.machine}")
            for t_id in pt.completed_tasks:
                if t_id not in task_ids:
                    errors.append(f"perturbation: unknown completed task {t_id}")
            for m_id, st in pt.machine_states.items():
                if m_id not in machine_ids:
                    errors.append(f"perturbation: unknown machine state {m_id}")
                if st.zone not in zone_ids:
                    errors.append(f"perturbation: unknown zone {st.zone}")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    # convenience lookups
    def machine(self, machine_id: str) -> Machine:
        return next(m for m in self.fleet if m.id == machine_id)

    def task(self, task_id: str) -> Task:
        return next(t for t in self.mission.tasks if t.id == task_id)

    @property
    def is_feasible(self) -> bool:
        return self.ground_truth.feasible


def apply_perturbation(scenario: Scenario) -> Scenario:
    """Return the replanning scenario produced by ``scenario.perturbation``."""
    p = scenario.perturbation
    if p is None:
        raise ValueError(f"scenario {scenario.id} has no perturbation")
    done = set(p.completed_tasks)
    fleet = []
    for m in scenario.fleet:
        if m.id == p.machine:
            continue
        st = p.machine_states.get(m.id)
        if st is None:
            st = MachineState(
                zone=m.start_zone,
                available_from=max(p.time, m.available_from),
                energy=m.start_energy,
            )
        fleet.append(
            m.model_copy(
                update={
                    "start_zone": st.zone,
                    "available_from": st.available_from,
                    "initial_energy": st.energy,
                }
            )
        )
    tasks = [
        t.model_copy(update={"precedence": [q for q in t.precedence if q not in done]})
        for t in scenario.mission.tasks
        if t.id not in done
    ]
    return Scenario(
        id=f"{scenario.id}@{p.kind}",
        tier=scenario.tier,
        domain=scenario.domain,
        description=f"{scenario.description} [after {p.kind} of {p.machine} at t={p.time}]",
        fleet=fleet,
        site=scenario.site,
        mission=Mission(tasks=tasks),
        ground_truth=p.ground_truth,
    )
