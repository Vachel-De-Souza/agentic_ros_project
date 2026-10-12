"""Bundled scenarios: integrity, reference plans, and infeasibility witnesses."""

from __future__ import annotations

from collections import Counter

import pytest

from fleet_plan_bench.graph import SiteGraph
from fleet_plan_bench.io import (
    builtin_scenario_paths,
    find_scenario,
    load_builtin_scenarios,
    load_scenario,
)
from fleet_plan_bench.schemas import Plan, Scenario, ViolationCode, apply_perturbation
from fleet_plan_bench.validator import validate

SCENARIOS = load_builtin_scenarios()
IDS = [s.id for s in SCENARIOS]
C = ViolationCode


def test_catalogue_shape() -> None:
    assert 12 <= len(SCENARIOS) <= 15
    assert len(set(IDS)) == len(IDS)
    tiers = Counter(s.tier for s in SCENARIOS)
    assert set(tiers) == {"easy", "medium", "hard"}
    assert sum(not s.is_feasible for s in SCENARIOS) >= 4
    assert sum(s.perturbation is not None for s in SCENARIOS) >= 1
    for path in builtin_scenario_paths():
        assert path.parent.name == load_scenario(path).tier
        assert path.stem == find_scenario(path.stem).id


def test_easy_tier_is_homogeneous() -> None:
    for s in SCENARIOS:
        if s.tier == "easy":
            assert len({m.type for m in s.fleet}) == 1, s.id


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_reference_plan_matches_ground_truth(scenario: Scenario) -> None:
    gt = scenario.ground_truth
    if gt.feasible:
        assert gt.reference_plan is not None, "feasible scenarios ship a witness plan"
        report = validate(scenario, gt.reference_plan)
        assert report.valid, report.summary()
    else:
        assert gt.reference_plan is None
        assert gt.reason


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.perturbation], ids=lambda s: s.id)
def test_perturbation_reference_plan(scenario: Scenario) -> None:
    after = apply_perturbation(scenario)
    assert scenario.perturbation is not None
    assert scenario.perturbation.machine not in {m.id for m in after.fleet}
    if after.is_feasible:
        assert after.ground_truth.reference_plan is not None
        report = validate(after, after.ground_truth.reference_plan)
        assert report.valid, report.summary()


# --- infeasibility witnesses: independent arguments, plus a natural attempt that fails ---


def _plan(*assignments: dict[str, object]) -> Plan:
    return Plan.model_validate({"assignments": list(assignments)})


def _codes(scenario: Scenario, plan: Plan) -> set[ViolationCode]:
    return {v.code for v in validate(scenario, plan).violations}


def test_e04_no_machine_can_spray() -> None:
    s = find_scenario("e04_spray_without_sprayer")
    assert not any("spray" in m.capabilities for m in s.fleet)
    plan = _plan(
        {"machine": "mower_1", "task": "mow_a", "route": ["barn", "lane", "block_a"],
         "start": 3, "end": 13},
        {"machine": "mower_1", "task": "spray_a", "route": ["block_a"], "start": 13, "end": 19},
        {"machine": "mower_2", "task": "mow_b", "route": ["barn", "lane", "block_b"],
         "start": 3.5, "end": 15.5},
    )  # fmt: skip
    assert _codes(s, plan) == {C.CAPABILITY_MISSING}


def test_m04_vent_shaft_out_of_range() -> None:
    s = find_scenario("m04_vent_shaft_out_of_range")
    g = SiteGraph(s.site)
    m = s.fleet[0]
    usable = m.battery_capacity * 0.9 / m.energy_per_distance
    for station in s.site.charging_stations:
        sp = g.shortest_path(station, "vent_shaft")
        assert sp is not None and sp[1] > usable
    plan = _plan(
        {"machine": "hauler_1", "task": "inspect_pump", "route": ["depot", "crosscut",
         "pump_station"], "start": 15, "end": 25},
        {"machine": "hauler_1", "task": "deliver_filters", "route": ["pump_station", "crosscut",
         "depot", "crosscut", "far_drift", "vent_shaft"], "charging_stops": [{"zone": "depot"}],
         "start": 100, "end": 108},
    )  # fmt: skip
    assert C.ENERGY_DEPLETED in _codes(s, plan)


def test_m05_beam_too_heavy() -> None:
    s = find_scenario("m05_precast_overweight")
    beam = s.task("deliver_beam")
    assert all(
        beam.payload_demand > m.payload_capacity
        for m in s.fleet
        if beam.required_capability in m.capabilities
    )
    plan = _plan(
        {"machine": "flatbed_1", "task": "deliver_slabs", "route": ["laydown", "site_road",
         "block_1"], "start": 4, "end": 14},
        {"machine": "flatbed_2", "task": "deliver_beam", "route": ["laydown", "site_road",
         "block_2"], "start": 5, "end": 17},
        {"machine": "telehandler_1", "task": "lift_beam", "route": ["laydown", "site_road",
         "block_2"], "start": 17, "end": 25},
    )  # fmt: skip
    assert _codes(s, plan) == {C.PAYLOAD_EXCEEDED}


def test_h03_chain_cannot_meet_deadline() -> None:
    s = find_scenario("h03_pour_deadline")
    chain = [s.task(t) for t in ("formwork_east", "pour_east", "inspect_east")]
    g = SiteGraph(s.site)
    fastest = max(m.speed for m in s.fleet)
    sp = g.shortest_path("compound", "slab_east")
    assert sp is not None
    lower_bound = sp[1] / fastest + sum(t.duration for t in chain)
    tw = chain[-1].time_window
    assert tw is not None and lower_bound > tw.latest_end
    plan = _plan(
        {"machine": "carpenter_rig_1", "task": "formwork_east", "route": ["compound",
         "slab_east"], "start": 2, "end": 12},
        {"machine": "pump_truck_1", "task": "pour_east", "route": ["compound", "slab_east"],
         "start": 12, "end": 22},
        {"machine": "inspection_cart_1", "task": "inspect_east", "route": ["compound",
         "slab_east"], "start": 22, "end": 32},
        {"machine": "carpenter_rig_1", "task": "formwork_west", "route": ["slab_east",
         "compound", "slab_west"], "start": 17, "end": 27},
    )  # fmt: skip
    assert _codes(s, plan) == {C.TIME_WINDOW_VIOLATED}


def test_h04_stope_3_unreachable() -> None:
    s = find_scenario("h04_flooded_drift")
    g = SiteGraph(s.site)
    for m in s.fleet:
        assert g.shortest_path(m.start_zone, "stope_3") is None
    plan = _plan(
        {"machine": "bolter_1", "task": "bolt_1", "route": ["shop", "main_drift", "stope_1"],
         "start": 17, "end": 37},
        {"machine": "loader_1", "task": "load_2", "route": ["shop", "main_drift", "stope_2"],
         "start": 15, "end": 30},
        {"machine": "loader_1", "task": "load_1", "route": ["stope_2", "main_drift", "stope_1"],
         "start": 42, "end": 57},
        {"machine": "bolter_1", "task": "bolt_3", "route": ["stope_1", "main_drift",
         "flooded_drift", "stope_3"], "start": 54, "end": 74},
    )  # fmt: skip
    assert _codes(s, plan) == {C.NO_GO_ZONE}
