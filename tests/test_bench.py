from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fleet_plan_bench.bench import (
    compute_metrics,
    markdown_report,
    run_benchmark,
    run_episode,
    write_results,
)
from fleet_plan_bench.io import find_scenario, load_builtin_scenarios
from fleet_plan_bench.planners import GreedyPlanner, PlannerUnavailableError, RepairFeedback
from fleet_plan_bench.schemas import Infeasible, Plan, Scenario


class Scripted:
    """Returns pre-baked outputs in order and records the feedback it received."""

    repairable = True

    def __init__(self, outputs: list[Any], name: str = "scripted") -> None:
        self.name = name
        self.outputs = list(outputs)
        self.feedback: list[RepairFeedback | None] = []
        self.last_usage = None

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Any:
        self.feedback.append(feedback)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture
def e01() -> Scenario:
    return find_scenario("e01_orchard_mowing")


def _good(s: Scenario) -> Plan:
    assert s.ground_truth.reference_plan is not None
    return s.ground_truth.reference_plan


def _broken(s: Scenario, **change: Any) -> Plan:
    p = _good(s).model_copy(deep=True)
    for k, v in change.items():
        setattr(p.assignments[0], k, v)
    return p


def test_repair_loop_feeds_back_typed_violations(e01: Scenario) -> None:
    planner = Scripted([_broken(e01, end=0.5), _good(e01)])
    ep = run_episode(planner, e01)
    assert [a.outcome for a in ep.attempts] == ["invalid_plan", "valid_plan"]
    fb = planner.feedback[1]
    assert fb is not None and fb.attempt == 1
    assert {v.code.value for v in fb.violations} == {"DURATION_TOO_SHORT"}
    m = compute_metrics([ep])[0]
    assert m.first_attempt_feasibility == 0
    assert m.post_repair_feasibility == 1
    assert m.repair_success == 1


def test_repair_attempts_are_capped(e01: Scenario) -> None:
    bad = [_broken(e01, machine=f"ghost_{i}") for i in range(10)]
    ep = run_episode(Scripted(bad), e01, max_repairs=3)
    assert len(ep.attempts) == 4
    assert all(a.hallucinated for a in ep.attempts)
    assert compute_metrics([ep])[0].hallucinated_reference_rate == 1


def test_identical_resubmission_stops_early(e01: Scenario) -> None:
    ep = run_episode(Scripted([_broken(e01, machine="ghost")]), e01)
    assert len(ep.attempts) == 2


def test_non_repairable_planner_gets_one_attempt(e01: Scenario) -> None:
    planner = Scripted([_broken(e01, end=0.5), _good(e01)])
    planner.repairable = False
    assert len(run_episode(planner, e01).attempts) == 1


def test_planner_errors_are_scored(e01: Scenario) -> None:
    ep = run_episode(Scripted([RuntimeError("garbled"), _good(e01)]), e01)
    assert ep.first.outcome == "error"
    assert ep.first.violations == {"SCHEMA_INVALID": 1}
    assert ep.final.outcome == "valid_plan"


def test_infeasibility_precision_recall() -> None:
    scenarios = load_builtin_scenarios()
    always_no = Scripted([Infeasible(reason="nope")], name="pessimist")
    eps = run_benchmark([always_no], scenarios)
    m = compute_metrics(eps)[0]
    n_inf = sum(not s.is_feasible for s in scenarios)
    assert m.infeasibility_recall == 1
    assert m.infeasibility_precision == pytest.approx(n_inf / len(eps))
    assert m.false_infeasible == len(eps) - n_inf
    assert m.first_attempt_feasibility == 0


def test_greedy_benchmark_end_to_end(tmp_path: Path) -> None:
    scenarios = load_builtin_scenarios()
    eps = run_benchmark([GreedyPlanner()], scenarios)
    assert len(eps) == len(scenarios) + sum(s.perturbation is not None for s in scenarios)
    assert any(e.perturbed for e in eps)
    m = compute_metrics(eps)[0]
    assert m.first_attempt_feasibility == 1
    assert m.infeasibility_precision == 1 and m.infeasibility_recall == 1
    assert m.makespan_gap_vs_reference == pytest.approx(0)
    out = tmp_path / "results.json"
    write_results(out, eps, [m])
    data = json.loads(out.read_text())
    assert data["metrics"][0]["planner"] == "greedy"
    assert len(data["episodes"]) == len(eps)
    md = markdown_report(eps, [m])
    assert "| greedy |" in md and "h05_excavator_breakdown@machine_failure" in md


def test_unavailable_planner_is_retried_then_recovers(e01: Scenario) -> None:
    planner = Scripted([PlannerUnavailableError("524"), _good(e01)])
    lines: list[str] = []
    ep = run_episode(planner, e01, retry_backoff_s=0, progress=lines.append)
    assert [a.outcome for a in ep.attempts] == ["valid_plan"]
    assert len(planner.feedback) == 2  # the retry re-sent the same request
    assert lines and "valid_plan" in lines[0] and "e01_orchard_mowing" in lines[0]


def test_persistent_unavailability_is_infra_error_and_not_scored(e01: Scenario) -> None:
    down = Scripted([PlannerUnavailableError("connection refused")], name="down")
    ep = run_episode(down, e01, retries=2, retry_backoff_s=0)
    assert [a.outcome for a in ep.attempts] == ["infra_error"]
    assert ep.infra_failed
    assert ep.first.violations == {} and not ep.first.hallucinated
    ok = run_episode(Scripted([_good(e01)], name="down"), e01)
    m = compute_metrics([ep, ok])[0]
    assert m.infra_failed_episodes == 1 and m.episodes == 1
    assert m.hallucinated_reference_rate == 0
