"""Handler tests: no ROS needed (run with plain pytest or colcon test)."""

from __future__ import annotations

import json

from fleet_plan_bench.io import find_scenario
from fleet_plan_validator_ros.handler import handle


def _reference_plan(scenario_id: str) -> str:
    plan = find_scenario(scenario_id).ground_truth.reference_plan
    assert plan is not None
    return plan.model_dump_json()


def test_valid_reference_plan_by_scenario_id() -> None:
    r = handle("e01_orchard_mowing", _reference_plan("e01_orchard_mowing"))
    assert r.valid and r.violation_codes == [] and not r.error
    assert json.loads(r.report_json)["valid"] is True


def test_default_scenario_and_scenario_as_json_text() -> None:
    plan = _reference_plan("m03_mine_bench")
    assert handle("", plan, default_scenario="m03_mine_bench").valid
    scenario_json = find_scenario("m03_mine_bench").model_dump_json()
    assert handle(scenario_json, plan).valid


def test_violations_are_reported() -> None:
    data = json.loads(_reference_plan("e01_orchard_mowing"))
    data["assignments"][0]["machine"] = "ghost"
    r = handle("e01_orchard_mowing", json.dumps(data))
    assert not r.valid
    assert r.violation_codes[0] == "UNKNOWN_MACHINE"


def test_unparseable_plan_is_schema_invalid() -> None:
    r = handle("e01_orchard_mowing", "{not json")
    assert not r.valid and r.violation_codes == ["SCHEMA_INVALID"] and not r.error


def test_infeasible_declaration_checked_against_ground_truth() -> None:
    decl = json.dumps({"kind": "infeasible", "reason": "no sprayer"})
    r = handle("e04_spray_without_sprayer", decl)
    assert r.declared_infeasible and r.agrees_with_ground_truth and not r.valid
    assert not handle("e01_orchard_mowing", decl).agrees_with_ground_truth


def test_perturbed_scenario() -> None:
    s = find_scenario("h05_excavator_breakdown")
    assert s.perturbation is not None
    plan = s.perturbation.ground_truth.reference_plan
    assert plan is not None
    assert handle(s.id, plan.model_dump_json(), perturbed=True).valid
    assert not handle(s.id, plan.model_dump_json()).valid


def test_bad_scenario_is_an_error_not_an_exception() -> None:
    r = handle("no_such_scenario", "{}")
    assert r.error and not r.valid
    assert handle("", "{}").error
