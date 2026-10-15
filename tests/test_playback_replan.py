"""Layout, playback timeline and mid-mission failure split (all ROS-free)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from fleet_plan_bench.io import find_scenario, load_builtin_scenarios
from fleet_plan_bench.layout import layout
from fleet_plan_bench.planners import GreedyPlanner
from fleet_plan_bench.playback import Timeline
from fleet_plan_bench.replan import merge, split_at_failure
from fleet_plan_bench.schemas import Plan, Scenario
from fleet_plan_bench.validator import validate


@pytest.mark.parametrize("scenario", load_builtin_scenarios(), ids=lambda s: s.id)
def test_layout_places_every_zone_deterministically(scenario: Scenario) -> None:
    a, b = layout(scenario.site), layout(scenario.site)
    assert a == b
    assert set(a) == {z.id for z in scenario.site.zones}
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in a.values())


def test_layout_keeps_given_positions(toy_dict: dict[str, Any]) -> None:
    toy_dict["site"]["zones"][0]["pos"] = [100.0, 50.0]
    pos = layout(Scenario.model_validate(toy_dict).site)
    assert pos["D"] == (100.0, 50.0)
    # unconstrained neighbours land at roughly their road distance
    d = math.dist(pos["D"], pos["A"])
    assert 5 < d < 20


def test_timeline_states(toy: Scenario, good_plan: Plan) -> None:
    tl = Timeline(toy, good_plan)
    s = tl.state_at("m1", 0.5)  # D -> A takes 1 time unit
    assert s.status == "drive" and s.task == "t1"
    d, a = tl.positions["D"], tl.positions["A"]
    assert (s.x, s.y) == pytest.approx(((d[0] + a[0]) / 2, (d[1] + a[1]) / 2))
    assert s.energy == pytest.approx(95)
    assert tl.state_at("m1", 3).status == "work"
    assert tl.state_at("m2", 5).status == "wait"  # arrived at B at 4, starts at 6
    assert tl.state_at("m1", 50).status == "done"
    assert tl.end_time == 11


def test_timeline_shows_charging(toy_dict: dict[str, Any], plan_dict: dict[str, Any]) -> None:
    toy_dict["fleet"][1]["initial_energy"] = 5
    t2 = next(a for a in plan_dict["assignments"] if a["task"] == "t2")
    t2.update(charging_stops=[{"zone": "D"}], start=9, end=13)
    tl = Timeline(Scenario.model_validate(toy_dict), Plan.model_validate(plan_dict))
    s = tl.state_at("m2", 2.5)
    assert s.status == "charge" and 5 < s.energy < 30


def test_split_at_failure_on_h05_and_replan() -> None:
    s = find_scenario("h05_excavator_breakdown")
    plan = s.ground_truth.reference_plan
    assert plan is not None
    remaining, committed = split_at_failure(s, plan, "excavator_1", 50)
    done = {a.task for a in committed}
    # excavator_1 had finished dig_1; dig_3 (and the hauls that need it) go back to the pool
    assert "dig_1" in done and "dig_3" not in done and "haul_3" not in done
    assert "excavator_1" not in {m.id for m in remaining.fleet}
    remaining_ids = {t.id for t in remaining.mission.tasks}
    assert remaining_ids.isdisjoint(done)
    assert remaining_ids | done == {t.id for t in s.mission.tasks}
    for m in remaining.fleet:
        assert m.available_from >= 50
    # every remaining task's committed predecessors are turned into an earliest start
    for task in remaining.mission.tasks:
        assert not set(task.precedence) & done
    replan = GreedyPlanner().plan(remaining)
    assert isinstance(replan, Plan)
    assert validate(remaining, replan).valid
    full = merge(committed, replan)
    assert {a.task for a in full.assignments} == {t.id for t in s.mission.tasks}


def test_split_rejects_unknown_machine(toy: Scenario, good_plan: Plan) -> None:
    with pytest.raises(ValueError, match="unknown machine"):
        split_at_failure(toy, good_plan, "ghost", 1)
