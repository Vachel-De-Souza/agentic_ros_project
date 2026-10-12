"""Every validator check, with passing and failing cases, on the toy scenario."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from fleet_plan_bench.schemas import Plan, Scenario, ValidationReport, ViolationCode
from fleet_plan_bench.validator import ValidatorConfig, validate, validate_raw

C = ViolationCode
Mut = Callable[[dict[str, Any]], None]


def run(scenario: dict[str, Any], plan: dict[str, Any], **cfg: Any) -> ValidationReport:
    return validate(
        Scenario.model_validate(scenario), Plan.model_validate(plan), ValidatorConfig(**cfg)
    )


def codes(report: ValidationReport) -> set[ViolationCode]:
    return {v.code for v in report.violations}


def asg(plan: dict[str, Any], task: str) -> dict[str, Any]:
    return next(a for a in plan["assignments"] if a["task"] == task)


def test_reference_plan_passes(toy_dict: dict[str, Any], plan_dict: dict[str, Any]) -> None:
    report = run(toy_dict, plan_dict)
    assert report.valid, report.summary()
    assert report.makespan == 11
    assert "PASS" in report.summary()


def test_validator_is_deterministic(toy: Scenario, good_plan: Plan) -> None:
    bad = good_plan.model_copy(deep=True)
    bad.assignments[0].machine = "ghost"
    r1, r2 = validate(toy, bad), validate(toy, bad)
    assert r1.model_dump_json() == r2.model_dump_json()


def test_schema_invalid(toy: Scenario) -> None:
    report = validate_raw(toy, {"assignments": [{"machine": "m1"}]})
    assert codes(report) == {C.SCHEMA_INVALID}
    assert report.has_hallucination
    assert validate_raw(toy, "not json").violations[0].code is C.SCHEMA_INVALID


# Each case: (scenario mutation, plan mutation, exact expected codes).
CASES: dict[str, tuple[Mut | None, Mut | None, set[ViolationCode]]] = {
    "unknown_machine": (
        None,
        lambda p: asg(p, "t3").update(machine="m9"),
        {C.UNKNOWN_MACHINE},
    ),
    "unknown_task": (
        None,
        lambda p: p["assignments"].append(
            {"machine": "m2", "task": "t9", "route": ["B"], "start": 20, "end": 21}
        ),
        {C.UNKNOWN_TASK},
    ),
    "unknown_zone": (
        None,
        lambda p: asg(p, "t1").update(route=["D", "Q", "A"]),
        {C.UNKNOWN_ZONE},
    ),
    "unknown_charging_zone": (
        None,
        lambda p: asg(p, "t2").update(charging_stops=[{"zone": "Q"}]),
        {C.UNKNOWN_ZONE},
    ),
    "task_unassigned": (
        None,
        lambda p: p["assignments"].remove(asg(p, "t3")),
        {C.TASK_UNASSIGNED},
    ),
    "task_duplicated": (
        None,
        lambda p: p["assignments"].append(
            {"machine": "m1", "task": "t3", "route": ["C"], "start": 11, "end": 14}
        ),
        {C.TASK_DUPLICATED},
    ),
    "capability_missing": (
        lambda s: s["fleet"][1].update(capabilities=["spray"]),
        None,
        {C.CAPABILITY_MISSING},
    ),
    "payload_exceeded": (
        lambda s: s["mission"]["tasks"][1].update(payload_demand=60),
        None,
        {C.PAYLOAD_EXCEEDED},
    ),
    "energy_depleted": (
        lambda s: s["fleet"][1].update(battery_capacity=15),
        None,
        {C.ENERGY_DEPLETED},
    ),
    "reserve_violated": (
        lambda s: s["fleet"][1].update(battery_capacity=21),
        None,
        {C.RESERVE_VIOLATED},
    ),
    "charging_at_non_station": (
        None,
        lambda p: asg(p, "t2").update(charging_stops=[{"zone": "A", "amount": 1}]),
        {C.INVALID_CHARGING_STOP},
    ),
    "charging_stop_not_on_route": (
        None,
        lambda p: asg(p, "t2").update(charging_stops=[{"zone": "C"}]),
        {C.INVALID_CHARGING_STOP},
    ),
    "edge_missing": (
        None,
        lambda p: asg(p, "t3").update(route=["A", "C"]),
        {C.EDGE_MISSING},
    ),
    "no_go_zone": (
        None,
        lambda p: asg(p, "t3").update(route=["A", "X", "C"]),
        {C.NO_GO_ZONE},
    ),
    "no_go_edge": (
        lambda s: s["fleet"][1].update(battery_capacity=100, speed=10),
        lambda p: asg(p, "t2").update(route=["D", "B"]),
        {C.NO_GO_EDGE},
    ),
    "route_start_mismatch": (
        None,
        lambda p: asg(p, "t3").update(route=["B", "C"]),
        {C.ROUTE_START_MISMATCH},
    ),
    "route_end_mismatch": (
        None,
        lambda p: asg(p, "t3").update(route=["A", "B"]),
        {C.ROUTE_END_MISMATCH},
    ),
    "precedence_violated": (
        None,
        lambda p: asg(p, "t2").update(start=5, end=9),
        {C.PRECEDENCE_VIOLATED},
    ),
    "time_window_violated": (
        lambda s: s["mission"]["tasks"][2].update(time_window={"latest_end": 10}),
        None,
        {C.TIME_WINDOW_VIOLATED},
    ),
    "time_window_too_early": (
        lambda s: s["mission"]["tasks"][2].update(time_window={"earliest_start": 9}),
        None,
        {C.TIME_WINDOW_VIOLATED},
    ),
    "machine_overlap": (
        None,
        lambda p: asg(p, "t3").update(start=5, end=8),
        {C.MACHINE_OVERLAP},
    ),
    "travel_time_infeasible": (
        lambda s: s["fleet"][1].update(speed=2),
        None,
        {C.TRAVEL_TIME_INFEASIBLE},
    ),
    "duration_too_short": (
        None,
        lambda p: asg(p, "t1").update(end=5),
        {C.DURATION_TOO_SHORT},
    ),
}


@pytest.mark.parametrize("name", list(CASES))
def test_failing_cases(name: str, toy_dict: dict[str, Any], plan_dict: dict[str, Any]) -> None:
    mut_s, mut_p, expected = CASES[name]
    if mut_s:
        mut_s(toy_dict)
    if mut_p:
        mut_p(plan_dict)
    report = run(toy_dict, plan_dict)
    assert not report.valid
    assert codes(report) == expected, report.summary()
    for v in report.violations:
        assert v.message
        assert v.machine_ids or v.task_ids or v.zone_ids


def test_unknown_references_do_not_crash_downstream_checks(
    toy_dict: dict[str, Any], plan_dict: dict[str, Any]
) -> None:
    for a in plan_dict["assignments"]:
        a["machine"] = "ghost"
    report = run(toy_dict, plan_dict)
    assert codes(report) == {C.UNKNOWN_MACHINE}
    assert len(report.violations) == 3


def test_charging_stop_makes_low_battery_plan_valid(
    toy_dict: dict[str, Any], plan_dict: dict[str, Any]
) -> None:
    toy_dict["fleet"][1]["initial_energy"] = 5
    report = run(toy_dict, plan_dict)
    assert codes(report) == {C.ENERGY_DEPLETED}

    # charge to full at the depot (25 energy at rate 5 = 5 time units), then go
    asg(plan_dict, "t2").update(charging_stops=[{"zone": "D"}])
    report = run(toy_dict, plan_dict)
    assert codes(report) == {C.TRAVEL_TIME_INFEASIBLE}
    assert "charging" in report.violations[0].message

    asg(plan_dict, "t2").update(start=9, end=13)
    assert run(toy_dict, plan_dict).valid


def test_reserve_fraction_is_configurable(
    toy_dict: dict[str, Any], plan_dict: dict[str, Any]
) -> None:
    toy_dict["fleet"][1]["battery_capacity"] = 21
    assert not run(toy_dict, plan_dict).valid
    assert run(toy_dict, plan_dict, reserve_fraction=0.0).valid


def test_single_lane_conflict_is_opt_in(
    toy_dict: dict[str, Any], plan_dict: dict[str, Any]
) -> None:
    toy_dict["site"]["edges"][0]["single_lane"] = True  # D-A, both machines leave D at t=0
    assert run(toy_dict, plan_dict).valid
    report = run(toy_dict, plan_dict, check_single_lane=True)
    assert codes(report) == {C.SINGLE_LANE_CONFLICT}
    assert set(report.violations[0].machine_ids) == {"m1", "m2"}


def test_summary_lists_codes(toy_dict: dict[str, Any], plan_dict: dict[str, Any]) -> None:
    asg(plan_dict, "t1").update(end=5)
    report = run(toy_dict, plan_dict)
    assert "FAIL" in report.summary()
    assert "DURATION_TOO_SHORT" in report.summary()
    assert report.counts() == {"DURATION_TOO_SHORT": 1}
