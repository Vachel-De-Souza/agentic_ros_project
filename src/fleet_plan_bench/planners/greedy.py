"""Deterministic greedy baseline.

Tasks are taken in topological order (ties: earliest deadline, then id). Each task goes
to the capable machine that would finish it earliest, travelling on shortest no-go-free
paths and detouring through a charging station (charge to full) when the direct route
would break the energy reserve. It prefers options that leave enough energy to reach a
charging station afterwards. It returns ``Infeasible`` when some task has no candidate.
It ignores repair feedback: it is deterministic and would produce the same plan again.
"""

from __future__ import annotations

from dataclasses import dataclass

from fleet_plan_bench.graph import SiteGraph
from fleet_plan_bench.planners.base import RepairFeedback, Usage
from fleet_plan_bench.planners.common import (
    can_reach_station,
    ceil3,
    explain_unassignable,
    topological_order,
    travel_options,
)
from fleet_plan_bench.schemas import (
    Assignment,
    ChargingStop,
    Infeasible,
    Machine,
    Plan,
    Scenario,
    Task,
)


@dataclass
class _State:
    zone: str
    time: float
    energy: float


@dataclass
class _Candidate:
    machine: Machine
    route: list[str]
    stops: list[ChargingStop]
    start: float
    end: float
    energy_after: float
    stranded: bool
    """True if the machine cannot reach a charging station after this task."""

    def key(self) -> tuple[bool, float, str]:
        return (self.stranded, self.end, self.machine.id)


class GreedyPlanner:
    name = "greedy"
    repairable = False  # deterministic: feedback would not change the plan

    def __init__(self, reserve_fraction: float = 0.10) -> None:
        self.reserve_fraction = reserve_fraction
        self.last_usage: Usage | None = None

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Plan | Infeasible:
        g = SiteGraph(scenario.site)
        order = topological_order(scenario.mission.tasks)
        if order is None:
            return Infeasible(reason="task precedence contains a cycle", planner=self.name)
        states = {
            m.id: _State(m.start_zone, m.available_from, m.start_energy) for m in scenario.fleet
        }
        done: dict[str, float] = {}
        assignments: list[Assignment] = []
        for task in order:
            ready = max((done[p] for p in task.precedence), default=0.0)
            best: _Candidate | None = None
            for m in scenario.fleet:
                if task.required_capability not in m.capabilities:
                    continue
                if task.payload_demand > m.payload_capacity:
                    continue
                cand = self._candidate(g, m, states[m.id], task, ready)
                if cand is not None and (best is None or cand.key() < best.key()):
                    best = cand
            if best is None:
                reason = explain_unassignable(g, scenario.fleet, task) or (
                    f"greedy search found no machine that can reach and finish {task.id} in time"
                )
                return Infeasible(reason=reason, planner=self.name)
            m = best.machine
            assignments.append(
                Assignment(
                    machine=m.id,
                    task=task.id,
                    route=best.route,
                    start=best.start,
                    end=best.end,
                    charging_stops=best.stops,
                )
            )
            states[m.id] = _State(task.zone, best.end, best.energy_after)
            done[task.id] = best.end
        return Plan(assignments=assignments, planner=self.name)

    def _candidate(
        self, g: SiteGraph, m: Machine, st: _State, task: Task, ready: float
    ) -> _Candidate | None:
        best: _Candidate | None = None
        for opt in travel_options(g, m, st.zone, task.zone, st.energy, self.reserve_fraction):
            stranded = not can_reach_station(
                g, m, task.zone, opt.energy_after, self.reserve_fraction
            )
            start = max(st.time + opt.duration, ready)
            if task.time_window is not None:
                start = max(start, task.time_window.earliest_start)
            start = ceil3(start)
            end = round(start + task.duration, 6)
            if task.time_window is not None and end > task.time_window.latest_end + 1e-9:
                continue
            cand = _Candidate(m, opt.route, opt.stops, start, end, opt.energy_after, stranded)
            if best is None or cand.key() < best.key():
                best = cand
        return best
