"""Helpers shared by the built-in planners."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from fleet_plan_bench.graph import SiteGraph
from fleet_plan_bench.schemas import ChargingStop, Machine, Task

INF = float("inf")


@dataclass
class TravelOption:
    route: list[str]
    stops: list[ChargingStop]
    duration: float
    """Travel plus charging time."""
    energy_after: float


def drive(g: SiteGraph, m: Machine, path: list[str], energy: float, reserve: float) -> float | None:
    """Energy after driving ``path``, or None if it drops below ``reserve`` on the way."""
    for a, b in pairwise(path):
        edge = g.edge(a, b)
        assert edge is not None
        energy -= edge.distance * m.energy_per_distance
        if energy < reserve - 1e-9:
            return None
    return energy


def travel_options(
    g: SiteGraph, m: Machine, src: str, dst: str, energy: float, reserve_fraction: float
) -> list[TravelOption]:
    """Direct shortest path, plus one detour per charging station (charge to full there)."""
    reserve = reserve_fraction * m.battery_capacity
    out: list[TravelOption] = []
    direct = g.shortest_path(src, dst)
    if direct is not None:
        e = drive(g, m, direct[0], energy, reserve)
        if e is not None:
            out.append(TravelOption(direct[0], [], direct[1] / m.speed, e))
    for s in sorted(g.stations):
        leg1 = g.shortest_path(src, s)
        leg2 = g.shortest_path(s, dst)
        if leg1 is None or leg2 is None:
            continue
        e_at_s = drive(g, m, leg1[0], energy, reserve)
        if e_at_s is None:
            continue
        e = drive(g, m, leg2[0], m.battery_capacity, reserve)
        if e is None:
            continue
        charge_t = (m.battery_capacity - e_at_s) / m.charge_rate
        t = (leg1[1] + leg2[1]) / m.speed + charge_t
        out.append(TravelOption(leg1[0] + leg2[0][1:], [ChargingStop(zone=s)], t, e))
    return out


def can_reach_station(
    g: SiteGraph, m: Machine, zone: str, energy: float, reserve_fraction: float
) -> bool:
    if not g.stations:
        return True
    reserve = reserve_fraction * m.battery_capacity
    for s in sorted(g.stations):
        sp = g.shortest_path(zone, s)
        if sp is not None and drive(g, m, sp[0], energy, reserve) is not None:
            return True
    return False


def topological_order(tasks: list[Task]) -> list[Task] | None:
    """Kahn's algorithm, ties broken by deadline then id. None if precedence has a cycle."""
    by_id = {t.id: t for t in tasks}
    indeg = {t.id: len(t.precedence) for t in tasks}
    succ: dict[str, list[str]] = {t.id: [] for t in tasks}
    for t in tasks:
        for p in t.precedence:
            succ[p].append(t.id)

    def key(tid: str) -> tuple[float, str]:
        tw = by_id[tid].time_window
        return (tw.latest_end if tw else INF, tid)

    ready = sorted((tid for tid, d in indeg.items() if d == 0), key=key)
    order: list[Task] = []
    while ready:
        tid = ready.pop(0)
        order.append(by_id[tid])
        for s in succ[tid]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
        ready.sort(key=key)
    return order if len(order) == len(tasks) else None


def ceil3(x: float) -> float:
    """Round a time up to 3 decimals (waiting is always allowed) so plans print cleanly."""
    return math.ceil(round(x * 1000, 6)) / 1000


def explain_unassignable(g: SiteGraph, fleet: list[Machine], task: Task) -> str | None:
    """A structural reason no machine can ever do ``task``, or None."""
    capable = [m for m in fleet if task.required_capability in m.capabilities]
    if not capable:
        return f"no machine has capability {task.required_capability!r} needed by {task.id}"
    if all(task.payload_demand > m.payload_capacity for m in capable):
        return f"task {task.id} payload {task.payload_demand:g} exceeds every capable machine"
    if all(g.shortest_path(m.start_zone, task.zone) is None for m in capable):
        return f"task {task.id} zone {task.zone} is unreachable without entering no-go areas"
    return None
