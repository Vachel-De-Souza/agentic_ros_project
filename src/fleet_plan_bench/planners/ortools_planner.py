"""OR-Tools CP-SAT baseline (optional extra: ``pip install fleet-plan-bench[ortools]``).

Stage 1 (CP-SAT, exact for what it models): choose a machine for every task and
sequence each machine's tasks with shortest-path travel times, respecting capability,
payload, reachability, precedence and time windows, minimising makespan. Energy is NOT
in the model, so an INFEASIBLE proof from CP-SAT is a sound infeasibility proof.

Stage 2 (post-processing): walk the tasks in CP-SAT order, insert a charging detour
whenever the direct route would break the energy reserve, and re-time the schedule.
Re-timing can push a task past its window; the validator will then report it.
"""

from __future__ import annotations

from typing import Any

from fleet_plan_bench.graph import SiteGraph
from fleet_plan_bench.planners.base import RepairFeedback, Usage
from fleet_plan_bench.planners.common import (
    ceil3,
    explain_unassignable,
    topological_order,
    travel_options,
)
from fleet_plan_bench.schemas import Assignment, Infeasible, Plan, Scenario

SCALE = 1000  # CP-SAT works on integers; times are scaled by this factor


class ORToolsPlanner:
    name = "ortools"

    def __init__(
        self, reserve_fraction: float = 0.10, max_deterministic_time: float = 10.0
    ) -> None:
        try:
            from ortools.sat.python import cp_model  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "ORToolsPlanner needs the 'ortools' extra: pip install 'fleet-plan-bench[ortools]'"
            ) from exc
        self.reserve_fraction = reserve_fraction
        self.max_deterministic_time = max_deterministic_time
        self.last_usage: Usage | None = None

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Plan | Infeasible:
        from ortools.sat.python import cp_model

        g = SiteGraph(scenario.site)
        tasks = scenario.mission.tasks
        topo = topological_order(tasks)
        if topo is None:
            return Infeasible(reason="task precedence contains a cycle", planner=self.name)
        for t in tasks:
            if (why := explain_unassignable(g, scenario.fleet, t)) is not None:
                return Infeasible(reason=why, planner=self.name)

        def travel(m_speed: float, a: str, b: str) -> int | None:
            sp = g.shortest_path(a, b)
            return None if sp is None else int(-(-sp[1] * SCALE // m_speed))  # ceil

        horizon = SCALE * int(
            sum(t.duration for t in tasks)
            + max((m.available_from for m in scenario.fleet), default=0)
            + sum(e.distance for e in scenario.site.edges)
            / min(m.speed for m in scenario.fleet)
            * len(tasks)
            + max((t.time_window.earliest_start for t in tasks if t.time_window), default=0.0)
            + 1
        )
        model = cp_model.CpModel()
        start = {t.id: model.new_int_var(0, horizon, f"s_{t.id}") for t in tasks}
        end = {t.id: model.new_int_var(0, horizon, f"e_{t.id}") for t in tasks}
        for t in tasks:
            model.add(end[t.id] == start[t.id] + round(t.duration * SCALE))
            for p in t.precedence:
                model.add(start[t.id] >= end[p])
            if t.time_window is not None:
                model.add(start[t.id] >= round(t.time_window.earliest_start * SCALE))
                if t.time_window.latest_end != float("inf"):
                    model.add(end[t.id] <= round(t.time_window.latest_end * SCALE))

        x: dict[tuple[str, str], cp_model.IntVar] = {}
        for m in scenario.fleet:
            cands = [
                t
                for t in tasks
                if t.required_capability in m.capabilities
                and t.payload_demand <= m.payload_capacity
                and g.shortest_path(m.start_zone, t.zone) is not None
            ]
            if not cands:
                continue
            arcs: list[tuple[int, int, Any]] = []
            empty = model.new_bool_var(f"empty_{m.id}")
            arcs.append((0, 0, empty))
            avail = round(m.available_from * SCALE)
            for i, t in enumerate(cands, start=1):
                xi = model.new_bool_var(f"x_{t.id}_{m.id}")
                x[(t.id, m.id)] = xi
                arcs.append((i, i, xi.Not()))
                first = model.new_bool_var(f"first_{t.id}_{m.id}")
                arcs.append((0, i, first))
                d0 = travel(m.speed, m.start_zone, t.zone)
                assert d0 is not None
                model.add(start[t.id] >= avail + d0).only_enforce_if(first)
                arcs.append((i, 0, model.new_bool_var(f"last_{t.id}_{m.id}")))
                for j, u in enumerate(cands, start=1):
                    if i == j:
                        continue
                    dij = travel(m.speed, t.zone, u.zone)
                    if dij is None:
                        continue
                    lit = model.new_bool_var(f"arc_{t.id}_{u.id}_{m.id}")
                    arcs.append((i, j, lit))
                    model.add(start[u.id] >= end[t.id] + dij).only_enforce_if(lit)
            model.add_circuit(arcs)
        for t in tasks:
            model.add_exactly_one(x[(t.id, m.id)] for m in scenario.fleet if (t.id, m.id) in x)

        makespan = model.new_int_var(0, horizon, "makespan")
        model.add_max_equality(makespan, list(end.values()))
        model.minimize(makespan)

        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.random_seed = 0
        solver.parameters.max_deterministic_time = self.max_deterministic_time
        status = solver.solve(model)
        self.last_usage = Usage(extra={"cp_status": solver.status_name(status)})
        if status == cp_model.INFEASIBLE:
            return Infeasible(
                reason="CP-SAT proved that no assignment satisfies capability, reachability, "
                "precedence and time windows (energy relaxed)",
                planner=self.name,
            )
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return Infeasible(
                reason=f"CP-SAT found no schedule within its limit ({solver.status_name(status)})",
                planner=self.name,
            )

        machine_of = {t: m for (t, m), v in x.items() if solver.value(v)}
        rank = {t.id: k for k, t in enumerate(topo)}
        order = sorted(tasks, key=lambda t: (solver.value(start[t.id]), rank[t.id]))
        machines = {m.id: m for m in scenario.fleet}
        state = {m.id: (m.start_zone, m.available_from, m.start_energy) for m in scenario.fleet}
        done: dict[str, float] = {}
        assignments: list[Assignment] = []
        for t in order:
            m = machines[machine_of[t.id]]
            zone, clock, energy = state[m.id]
            opts = travel_options(g, m, zone, t.zone, energy, self.reserve_fraction)
            if not opts:
                return Infeasible(
                    reason=f"{m.id} cannot reach {t.zone} for task {t.id} within its energy "
                    "reserve, even with a charging detour",
                    planner=self.name,
                )
            opt = min(opts, key=lambda o: (o.duration, len(o.stops)))
            s = max(clock + opt.duration, max((done[p] for p in t.precedence), default=0.0))
            if t.time_window is not None:
                s = max(s, t.time_window.earliest_start)
            s = ceil3(s)
            e = round(s + t.duration, 6)
            assignments.append(
                Assignment(
                    machine=m.id,
                    task=t.id,
                    route=opt.route,
                    start=s,
                    end=e,
                    charging_stops=opt.stops,
                )
            )
            state[m.id] = (t.zone, e, opt.energy_after)
            done[t.id] = e
        return Plan(assignments=assignments, planner=self.name)
