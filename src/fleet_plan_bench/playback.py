"""Turn a plan into a timeline of machine states, for visualisation and live demos.

Timing and energy come from the validator's own simulation, so what is animated is exactly
what was checked. Machines leave as soon as their previous task ends (eager departure),
travel and charge, wait at the task zone if early, then work from ``start`` to ``end``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fleet_plan_bench.layout import layout
from fleet_plan_bench.schemas import Plan, Scenario
from fleet_plan_bench.validator import ValidatorConfig
from fleet_plan_bench.validator.context import Context

Status = str  # "idle" | "drive" | "charge" | "wait" | "work" | "done"


@dataclass(frozen=True)
class Interval:
    t0: float
    t1: float
    status: Status
    a: str
    b: str
    """Zones: drive goes a -> b; every other status has a == b."""
    task: str | None
    e0: float
    e1: float


@dataclass(frozen=True)
class MachineState:
    machine: str
    x: float
    y: float
    heading: float
    status: Status
    zone: str | None
    task: str | None
    energy: float
    battery_capacity: float


class Timeline:
    def __init__(
        self,
        scenario: Scenario,
        plan: Plan,
        positions: dict[str, tuple[float, float]] | None = None,
        config: ValidatorConfig | None = None,
    ) -> None:
        self.scenario = scenario
        self.positions = positions or layout(scenario.site)
        ctx = Context.build(scenario, plan, config or ValidatorConfig())
        self.intervals: dict[str, list[Interval]] = {}
        for m in scenario.fleet:
            items: list[Interval] = []
            clock, zone, energy = m.available_from, m.start_zone, m.start_energy
            for leg in ctx.legs.get(m.id, []):
                a = leg.assignment
                if leg.depart > clock:
                    items.append(
                        Interval(clock, leg.depart, "idle", zone, zone, None, energy, energy)
                    )
                t = leg.depart
                for s in leg.segments:
                    if s.t0 > t:  # zero-length gaps (e.g. repeated zones)
                        items.append(Interval(t, s.t0, "wait", s.a, s.a, a.task, s.e0, s.e0))
                    status = "drive" if s.kind == "drive" else "charge"
                    items.append(Interval(s.t0, s.t1, status, s.a, s.b, a.task, s.e0, s.e1))
                    t = s.t1
                energy = leg.energy_end
                zone = leg.task.zone
                if a.start > t:
                    items.append(Interval(t, a.start, "wait", zone, zone, a.task, energy, energy))
                items.append(
                    Interval(max(a.start, t), a.end, "work", zone, zone, a.task, energy, energy)
                )
                clock = max(clock, a.end)
            items.append(Interval(clock, math.inf, "done", zone, zone, None, energy, energy))
            self.intervals[m.id] = items
        self.end_time = max(
            (iv[-2].t1 if len(iv) > 1 else 0.0 for iv in self.intervals.values()), default=0.0
        )

    def _xy(self, zone: str) -> tuple[float, float]:
        return self.positions.get(zone, (0.0, 0.0))

    def state_at(self, machine_id: str, t: float) -> MachineState:
        m = next(m for m in self.scenario.fleet if m.id == machine_id)
        items = self.intervals[machine_id]
        iv = next(
            (i for i in items if i.t0 <= t < i.t1), items[0] if t < items[0].t0 else items[-1]
        )
        span = iv.t1 - iv.t0
        f = 0.0 if not math.isfinite(span) or span <= 0 else min(max((t - iv.t0) / span, 0.0), 1.0)
        (xa, ya), (xb, yb) = self._xy(iv.a), self._xy(iv.b)
        x, y = xa + f * (xb - xa), ya + f * (yb - ya)
        heading = math.atan2(yb - ya, xb - xa) if iv.a != iv.b else self._last_heading(items, iv)
        return MachineState(
            machine=machine_id,
            x=x,
            y=y,
            heading=heading,
            status=iv.status,
            zone=None if iv.status == "drive" else iv.a,
            task=iv.task,
            energy=iv.e0 + f * (iv.e1 - iv.e0),
            battery_capacity=m.battery_capacity,
        )

    def _last_heading(self, items: list[Interval], iv: Interval) -> float:
        prev = [i for i in items if i.t1 <= iv.t0 and i.status == "drive"]
        if not prev:
            return 0.0
        (xa, ya), (xb, yb) = self._xy(prev[-1].a), self._xy(prev[-1].b)
        return math.atan2(yb - ya, xb - xa)
