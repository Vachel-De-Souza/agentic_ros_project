"""Shared state for validator checks, including a deterministic per-machine simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from fleet_plan_bench.graph import SiteGraph
from fleet_plan_bench.schemas import (
    Assignment,
    Machine,
    Plan,
    Scenario,
    Task,
    Violation,
    ViolationCode,
)


@dataclass(frozen=True)
class ValidatorConfig:
    reserve_fraction: float = 0.10
    """Energy must stay at or above this fraction of battery capacity after every edge."""
    tolerance: float = 1e-6
    """Slack for floating point comparisons of times and energies."""
    check_single_lane: bool = False
    """Experimental v0.2 check: single-lane space-time conflicts (assumes eager departure)."""


@dataclass
class EdgeTraversal:
    a: str
    b: str
    t0: float
    t1: float


@dataclass
class Segment:
    """One timed step of a leg: driving an edge, or charging at a zone."""

    kind: str
    """``drive`` or ``charge``."""
    a: str
    b: str
    """Same as ``a`` for a charge."""
    t0: float
    t1: float
    e0: float
    e1: float


@dataclass
class Leg:
    """Simulated execution of one assignment by its machine."""

    index: int
    assignment: Assignment
    task: Task
    origin: str
    """Where the machine actually is before this assignment."""
    depart: float
    distance: float = 0.0
    travel_time: float = 0.0
    charge_time: float = 0.0
    energy_start: float = 0.0
    energy_end: float = 0.0
    energy_violations: list[Violation] = field(default_factory=list)
    traversals: list[EdgeTraversal] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    """Timed drive/charge steps in order (used for playback)."""

    @property
    def arrival(self) -> float:
        return self.depart + self.travel_time + self.charge_time


@dataclass
class Context:
    scenario: Scenario
    plan: Plan
    config: ValidatorConfig
    graph: SiteGraph
    machines: dict[str, Machine]
    tasks: dict[str, Task]
    resolved: list[tuple[int, Assignment]]
    """Assignments whose machine and task exist (unknown zones are skipped downstream)."""
    legs: dict[str, list[Leg]] = field(default_factory=dict)
    """Per-machine legs ordered by start time."""

    @classmethod
    def build(cls, scenario: Scenario, plan: Plan, config: ValidatorConfig) -> Context:
        graph = SiteGraph(scenario.site)
        machines = {m.id: m for m in scenario.fleet}
        tasks = {t.id: t for t in scenario.mission.tasks}
        resolved = [
            (i, a)
            for i, a in enumerate(plan.assignments)
            if a.machine in machines and a.task in tasks
        ]
        ctx = cls(scenario, plan, config, graph, machines, tasks, resolved)
        ctx._simulate()
        return ctx

    def first_assignment(self, task_id: str) -> Assignment | None:
        return next((a for _, a in self.resolved if a.task == task_id), None)

    def _simulate(self) -> None:
        by_machine: dict[str, list[tuple[int, Assignment]]] = {}
        for i, a in self.resolved:
            by_machine.setdefault(a.machine, []).append((i, a))
        for m_id, items in by_machine.items():
            items.sort(key=lambda ia: (ia[1].start, ia[1].end, ia[0]))
            machine = self.machines[m_id]
            position = machine.start_zone
            clock = machine.available_from
            energy = machine.start_energy
            legs: list[Leg] = []
            for i, a in items:
                task = self.tasks[a.task]
                leg = Leg(index=i, assignment=a, task=task, origin=position, depart=clock)
                energy = self._simulate_leg(machine, leg, energy)
                legs.append(leg)
                position = task.zone
                clock = max(clock, a.end)
            self.legs[m_id] = legs

    def _simulate_leg(self, machine: Machine, leg: Leg, energy: float) -> float:
        a, cfg, g = leg.assignment, self.config, self.graph
        tol = cfg.tolerance
        reserve = cfg.reserve_fraction * machine.battery_capacity
        leg.energy_start = energy
        # unknown zones are reported by the reference check; skip them here
        stops = [s for s in a.charging_stops if s.zone in g.zones]
        t = leg.depart
        depleted = reserve_hit = False
        for k, zone in enumerate(a.route):
            while stops and stops[0].zone == zone:
                stop = stops.pop(0)
                if zone not in g.stations:
                    leg.energy_violations.append(
                        _v_charge(machine, a, zone, f"zone {zone} has no charging station")
                    )
                    continue
                room = max(0.0, machine.battery_capacity - energy)
                added = room if stop.amount is None else min(stop.amount, room)
                dt = added / machine.charge_rate
                if dt > 0:
                    leg.segments.append(
                        Segment("charge", zone, zone, t, t + dt, energy, energy + added)
                    )
                energy += added
                leg.charge_time += dt
                t += dt
            if k + 1 == len(a.route):
                break
            nxt = a.route[k + 1]
            edge = g.edge(zone, nxt) if zone != nxt else None  # None if a zone is unknown
            if edge is None:
                continue
            dist = edge.distance
            dt = dist / machine.speed
            if edge.single_lane:
                leg.traversals.append(EdgeTraversal(zone, nxt, t, t + dt))
            e_next = energy - dist * machine.energy_per_distance
            leg.segments.append(Segment("drive", zone, nxt, t, t + dt, energy, e_next))
            t += dt
            leg.distance += dist
            leg.travel_time += dt
            energy = e_next
            if energy < -tol and not depleted:
                depleted = True
                leg.energy_violations.append(
                    _violation_energy(
                        ViolationCode.ENERGY_DEPLETED,
                        machine,
                        a,
                        nxt,
                        f"{machine.id} runs out of energy reaching {nxt} on the way to task "
                        f"{a.task} (energy {energy:.2f} of {machine.battery_capacity:g})",
                    )
                )
            elif energy < reserve - tol and not reserve_hit and not depleted:
                reserve_hit = True
                leg.energy_violations.append(
                    _violation_energy(
                        ViolationCode.RESERVE_VIOLATED,
                        machine,
                        a,
                        nxt,
                        f"{machine.id} drops to {energy:.2f} energy at {nxt} on the way to task "
                        f"{a.task}, below the reserve of {reserve:.2f} "
                        f"({cfg.reserve_fraction:.0%} of {machine.battery_capacity:g})",
                    )
                )
        for stop in stops:
            leg.energy_violations.append(
                _v_charge(
                    machine,
                    a,
                    stop.zone,
                    f"charging stop at {stop.zone} does not match the route {a.route} (in order)",
                )
            )
        leg.energy_end = energy
        return energy


def _violation_energy(
    code: ViolationCode, machine: Machine, a: Assignment, zone: str, msg: str
) -> Violation:
    return Violation(
        code=code,
        message=msg,
        machine_ids=[machine.id],
        task_ids=[a.task],
        zone_ids=[zone],
    )


def _v_charge(machine: Machine, a: Assignment, zone: str, why: str) -> Violation:
    return _violation_energy(
        ViolationCode.INVALID_CHARGING_STOP, machine, a, zone, f"{machine.id} task {a.task}: {why}"
    )
