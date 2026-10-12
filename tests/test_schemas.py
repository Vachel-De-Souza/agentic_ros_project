from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from fleet_plan_bench.graph import SiteGraph
from fleet_plan_bench.io import load_plan, load_scenario, parse_planner_output
from fleet_plan_bench.schemas import (
    GroundTruth,
    Infeasible,
    MachineState,
    Perturbation,
    Plan,
    Scenario,
    ViolationCode,
    apply_perturbation,
)
from fleet_plan_bench.schemas.report import Check


def test_scenario_parses(toy: Scenario) -> None:
    assert toy.machine("m2").battery_capacity == 30
    assert toy.task("t2").precedence == ["t1"]
    assert toy.machine("m1").start_energy == 100


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["fleet"][0].update(start_zone="NOPE"), "unknown start_zone"),
        (lambda d: d["mission"]["tasks"][0].update(zone="NOPE"), "unknown zone"),
        (lambda d: d["mission"]["tasks"][0].update(precedence=["t9"]), "unknown predecessor"),
        (lambda d: d["site"]["edges"].append({"a": "D", "b": "Q", "distance": 1}), "unknown zone"),
        (lambda d: d["site"]["charging_stations"].append("Q"), "charging station"),
        (lambda d: d["fleet"].append(dict(d["fleet"][0])), "duplicate machine"),
    ],
)
def test_scenario_integrity_errors(toy_dict: dict[str, Any], mutate: Any, message: str) -> None:
    mutate(toy_dict)
    with pytest.raises(ValidationError, match=message):
        Scenario.model_validate(toy_dict)


def test_scenario_rejects_extra_fields(toy_dict: dict[str, Any]) -> None:
    toy_dict["fleet"][0]["warp_drive"] = True
    with pytest.raises(ValidationError):
        Scenario.model_validate(toy_dict)


def test_parse_planner_output_variants(plan_dict: dict[str, Any]) -> None:
    assert isinstance(parse_planner_output(plan_dict), Plan)
    assert isinstance(parse_planner_output(json.dumps(plan_dict)), Plan)
    out = parse_planner_output({"reason": "no tiller"})
    assert isinstance(out, Infeasible)
    assert out.reason == "no tiller"


def test_plan_makespan(good_plan: Plan) -> None:
    assert good_plan.makespan() == 11


def test_io_roundtrip_yaml_and_json(tmp_path: Any, toy_dict: dict[str, Any]) -> None:
    import yaml

    y = tmp_path / "s.yaml"
    y.write_text(yaml.safe_dump(toy_dict))
    j = tmp_path / "s.json"
    j.write_text(json.dumps(toy_dict))
    assert load_scenario(y) == load_scenario(j)
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"kind": "infeasible", "reason": "x"}))
    assert isinstance(load_plan(p), Infeasible)


def test_every_code_has_a_check() -> None:
    for code in ViolationCode:
        assert isinstance(code.check, Check)


def test_graph_shortest_path_avoids_no_go(toy: Scenario) -> None:
    g = SiteGraph(toy.site)
    path, dist = g.shortest_path("D", "C")  # type: ignore[misc]
    assert path == ["D", "A", "B", "C"]
    assert dist == 30
    assert g.shortest_path("D", "X") is None
    assert g.shortest_path("A", "A") == (["A"], 0.0)
    assert g.route_length(["D", "A", "A", "B"]) == 20


def test_apply_perturbation(toy: Scenario) -> None:
    toy = toy.model_copy(
        update={
            "perturbation": Perturbation(
                time=6,
                machine="m2",
                completed_tasks=["t1"],
                machine_states={"m1": MachineState(zone="A", available_from=6, energy=90)},
                ground_truth=GroundTruth(feasible=False, reason="no hauler left"),
            )
        }
    )
    after = apply_perturbation(toy)
    assert [m.id for m in after.fleet] == ["m1"]
    assert after.machine("m1").start_zone == "A"
    assert after.machine("m1").start_energy == 90
    assert [t.id for t in after.mission.tasks] == ["t2", "t3"]
    assert after.task("t2").precedence == []
    assert not after.is_feasible
