"""The live demo as a ROS-free state machine.

plan (with validator-driven repair) -> play back -> machine fails -> replan (with repair)
-> resume -> done. Everything the dashboard shows lives in ``DemoState``. A 3-D simulator
(Gazebo, phase 2) is reached only through the small ``Mover`` interface; the browser demo
uses ``NullMover`` and draws the map from the state.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from fleet_plan_bench.demo.style import (
    FAILURE_MARKER,
    HIDDEN_Z,
    hex_color,
    scale_for,
    vehicle_color,
)
from fleet_plan_bench.layout import layout
from fleet_plan_bench.planners import Planner, PlannerUnavailableError, RepairFeedback
from fleet_plan_bench.playback import Timeline
from fleet_plan_bench.replan import merge, split_at_failure
from fleet_plan_bench.schemas import Infeasible, Plan, Scenario, Violation, ViolationCode
from fleet_plan_bench.validator import validate


class Mover(Protocol):
    def set_pose(
        self, name: str, x: float, y: float, z: float, yaw: float, roll: float = 0.0
    ) -> None: ...


class NullMover:
    """For the browser-only demo: nothing to move, the dashboard map draws the state."""

    def set_pose(
        self, name: str, x: float, y: float, z: float, yaw: float, roll: float = 0.0
    ) -> None:
        pass


@dataclass
class DemoConfig:
    max_repairs: int = 3
    tick_hz: float = 10.0
    mission_seconds: float = 60.0
    """Wall-clock length of the playback; mission time is scaled to fit."""
    failure: tuple[str, float] | None = None
    """(machine, mission time). Defaults to the scenario's perturbation, if any."""
    fallback: Planner | None = None
    """Used if the main planner cannot produce a valid plan, so a live demo never stalls."""


@dataclass
class DemoState:
    phase: str = "ready"
    """ready | planning | executing | failure | replanning | done | failed"""
    mission_time: float = 0.0
    end_time: float = 0.0
    planner: str = ""
    scenario: dict[str, Any] = field(default_factory=dict)
    machines: dict[str, dict[str, Any]] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class DemoRunner:
    def __init__(
        self,
        scenario: Scenario,
        planner: Planner,
        mover: Mover,
        config: DemoConfig | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.scenario = scenario
        self.planner = planner
        self.mover = mover
        self.config = config or DemoConfig()
        self.sleep = sleep
        self.positions = layout(scenario.site)
        self.scale = scale_for(self.positions)
        # each vehicle gets a fixed offset so vehicles sharing a zone or road sit side by side
        n = max(len(scenario.fleet), 1)
        self.offsets = {
            m.id: (1.8 * math.cos(2 * math.pi * i / n), 1.8 * math.sin(2 * math.pi * i / n))
            for i, m in enumerate(scenario.fleet)
        }
        self.lock = threading.Lock()
        self.state = DemoState()
        self._init_state()

    # --- state helpers -----------------------------------------------------------------

    def _init_state(self) -> None:
        s = self.scenario
        failure = self.config.failure or (
            (s.perturbation.machine, s.perturbation.time) if s.perturbation else None
        )
        self.failure = failure
        with self.lock:
            self.state = DemoState(planner=self.planner.name)
            self.state.scenario = {
                "id": s.id,
                "description": s.description,
                "zones": [
                    {
                        "id": z.id,
                        "kind": z.kind,
                        "no_go": z.no_go,
                        "pos": self.positions[z.id],
                        "charger": z.id in s.site.charging_stations,
                    }
                    for z in s.site.zones
                ],
                "edges": [
                    {"a": e.a, "b": e.b, "no_go": e.no_go, "single_lane": e.single_lane}
                    for e in s.site.edges
                ],
                "tasks": [t.id for t in s.mission.tasks],
                "failure": {"machine": failure[0], "time": failure[1]} if failure else None,
            }
            for i, m in enumerate(s.fleet):
                x, y = self.positions[m.start_zone]
                x += self.offsets[m.id][0] / self.scale
                y += self.offsets[m.id][1] / self.scale
                self.state.machines[m.id] = {
                    "type": m.type,
                    "color": hex_color(vehicle_color(i)),
                    "status": "idle",
                    "task": None,
                    "zone": m.start_zone,
                    "x": x,
                    "y": y,
                    "battery": 100.0 * m.start_energy / m.battery_capacity,
                }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            st = self.state
            return {
                "phase": st.phase,
                "mission_time": st.mission_time,
                "end_time": st.end_time,
                "planner": st.planner,
                "scenario": st.scenario,
                "machines": {k: dict(v) for k, v in st.machines.items()},
                "attempts": list(st.attempts),
                "events": list(st.events[-60:]),
                "summary": dict(st.summary),
            }

    def _event(self, text: str, level: str = "info") -> None:
        with self.lock:
            self.state.events.append(
                {
                    "wall": time.time(),
                    "t": round(self.state.mission_time, 2),
                    "level": level,
                    "text": text,
                }
            )

    def _phase(self, phase: str) -> None:
        with self.lock:
            self.state.phase = phase

    # --- planning with repair ----------------------------------------------------------

    def _plan(self, scenario: Scenario, round_name: str) -> Plan | None:
        planners = [self.planner] + ([self.config.fallback] if self.config.fallback else [])
        for planner in planners:
            plan = self._plan_with(planner, scenario, round_name)
            if plan is not None:
                return plan
            if planner is not planners[-1]:
                self._event(
                    f"{planner.name} gave no valid plan; falling back to {planners[-1].name}",
                    "warn",
                )
        return None

    def _plan_with(self, planner: Planner, scenario: Scenario, round_name: str) -> Plan | None:
        self._current = planner
        feedback: RepairFeedback | None = None
        for k in range(self.config.max_repairs + 1):
            label = "first attempt" if k == 0 else f"repair {k}"
            self._event(f"[{round_name}] asking {planner.name} for a plan ({label})")
            t0 = time.monotonic()
            try:
                out = planner.plan(scenario, feedback)
            except PlannerUnavailableError as exc:
                self._event(f"{planner.name} unreachable: {exc}", "error")
                return None
            except Exception as exc:  # unparseable output is shown, then repaired
                self._record(round_name, planner.name, k, "error", [str(exc)[:300]], t0)
                feedback = RepairFeedback(
                    attempt=k + 1,
                    previous=Plan(assignments=[]),
                    violations=[Violation(code=ViolationCode.SCHEMA_INVALID, message=str(exc))],
                )
                continue
            if isinstance(out, Infeasible):
                self._record(round_name, planner.name, k, "declared_infeasible", [out.reason], t0)
                return None
            report = validate(scenario, out)
            msgs = [f"{v.code.value}: {v.message}" for v in report.violations]
            self._record(
                round_name, planner.name, k, "valid" if report.valid else "rejected", msgs, t0
            )
            if report.valid:
                self._event(f"validator accepted the plan (makespan {report.makespan:g})", "ok")
                return out
            self._event(f"validator rejected the plan: {len(msgs)} violation(s)", "warn")
            feedback = RepairFeedback(attempt=k + 1, previous=out, violations=report.violations)
        return None

    def _record(
        self, round_name: str, planner: str, k: int, outcome: str, details: list[str], t0: float
    ) -> None:
        usage = getattr(self._current, "last_usage", None)
        with self.lock:
            self.state.attempts.append(
                {
                    "round": round_name,
                    "planner": planner,
                    "attempt": k,
                    "outcome": outcome,
                    "details": details[:12],
                    "seconds": round(time.monotonic() - t0, 1),
                    "output_tokens": getattr(usage, "output_tokens", None),
                }
            )

    # --- playback ----------------------------------------------------------------------

    def _apply(self, tl: Timeline, t: float, frozen: set[str]) -> None:
        for m in self.scenario.fleet:
            if m.id in frozen:
                continue
            st = tl.state_at(m.id, t)
            dx, dy = self.offsets[m.id]
            x, y = st.x * self.scale + dx, st.y * self.scale + dy
            self.mover.set_pose(m.id, x, y, 0.6, st.heading)
            with self.lock:
                self.state.machines[m.id].update(
                    status=st.status,
                    task=st.task,
                    zone=st.zone,
                    x=x / self.scale,
                    y=y / self.scale,
                    heading=st.heading,
                    battery=round(100.0 * st.energy / st.battery_capacity, 1),
                )

    def _play(self, tl: Timeline, t_from: float, t_to: float, frozen: set[str]) -> None:
        rate = max(tl.end_time, 1.0) / self.config.mission_seconds  # mission units per second
        dt = 1.0 / self.config.tick_hz
        t = t_from
        while True:
            with self.lock:
                self.state.mission_time = t
            self._apply(tl, t, frozen)
            if t >= t_to:
                break
            self.sleep(dt)
            t = min(t + rate * dt, t_to)

    # --- the whole demo ----------------------------------------------------------------

    def run(self) -> None:
        self._init_state()
        self.mover.set_pose(FAILURE_MARKER, 0, 0, HIDDEN_Z, 0)
        self._phase("planning")
        self._event(f"scenario {self.scenario.id}: {self.scenario.description}")
        plan = self._plan(self.scenario, "initial")
        if plan is None:
            self._phase("failed")
            self._event("no valid plan; nothing is dispatched", "error")
            return
        tl = Timeline(self.scenario, plan, self.positions)
        with self.lock:
            self.state.end_time = tl.end_time
        self._phase("executing")
        self._event("plan dispatched to the fleet", "ok")
        frozen: set[str] = set()
        if self.failure and self.failure[1] < tl.end_time:
            machine, t_fail = self.failure
            self._play(tl, 0.0, t_fail, frozen)
            plan, tl = self._fail_and_replan(plan, tl, machine, t_fail, frozen)
            if plan is None:
                self._phase("failed")
                return
            self._phase("executing")
            self._event("replanned work dispatched; resuming", "ok")
            self._play(tl, t_fail, tl.end_time, frozen)
        else:
            self._play(tl, 0.0, tl.end_time, frozen)
        with self.lock:
            self.state.summary = {
                "makespan": round(tl.end_time, 2),
                "attempts": len(self.state.attempts),
                "rejected": sum(a["outcome"] != "valid" for a in self.state.attempts),
                "violations_caught": sum(
                    len(a["details"]) for a in self.state.attempts if a["outcome"] == "rejected"
                ),
            }
        self._phase("done")
        self._event(f"mission complete at t={tl.end_time:g}", "ok")

    def _fail_and_replan(
        self, plan: Plan, tl: Timeline, machine: str, t: float, frozen: set[str]
    ) -> tuple[Plan | None, Timeline]:
        self._phase("failure")
        st = tl.state_at(machine, t)
        dx, dy = self.offsets[machine]
        x, y = st.x * self.scale + dx, st.y * self.scale + dy
        frozen.add(machine)
        self.mover.set_pose(machine, x, y, 0.6, st.heading, roll=0.5)
        self.mover.set_pose(FAILURE_MARKER, x, y, 2.6, 0)
        with self.lock:
            self.state.machines[machine].update(status="failed", task=None)
        self._event(f"{machine} broke down at t={t:g}", "error")
        remaining, committed = split_at_failure(self.scenario, plan, machine, t)
        self._event(
            f"{len(committed)} assignments committed; "
            f"{len(remaining.mission.tasks)} tasks to replan"
        )
        self._phase("replanning")
        replan = self._plan(remaining, "replan")
        if replan is None:
            self._event("replanning failed; remaining work is not dispatched", "error")
            return None, tl
        merged = merge(committed, replan)
        live = self.scenario.model_copy(
            update={"fleet": [m for m in self.scenario.fleet if m.id != machine]}
        )
        new_tl = Timeline(live, merged, self.positions)
        # the failed machine keeps its frozen pose; add a placeholder for it in the timeline
        new_tl.intervals.setdefault(machine, tl.intervals[machine])
        with self.lock:
            self.state.end_time = new_tl.end_time
        return merged, new_tl
