"""Request handling without any ROS imports, so it can be unit-tested with plain pytest."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import yaml
from pydantic import ValidationError

from fleet_plan_bench.io import find_scenario, parse_planner_output
from fleet_plan_bench.schemas import Infeasible, Scenario, apply_perturbation
from fleet_plan_bench.validator import ValidatorConfig, validate, validate_raw


@dataclass
class Result:
    valid: bool = False
    declared_infeasible: bool = False
    agrees_with_ground_truth: bool = False
    violation_codes: list[str] = field(default_factory=list)
    summary: str = ""
    report_json: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


def load_scenario_text(text: str) -> Scenario:
    """Scenario from JSON text, YAML text, a built-in scenario id, or a file path."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("no scenario given and no default_scenario parameter set")
    if stripped.startswith("{"):
        return Scenario.model_validate(json.loads(stripped))
    if "\n" in stripped:
        return Scenario.model_validate(yaml.safe_load(stripped))
    return find_scenario(stripped)


def handle(
    scenario_text: str,
    plan_text: str,
    *,
    perturbed: bool = False,
    default_scenario: str = "",
    config: ValidatorConfig | None = None,
) -> Result:
    """Validate ``plan_text`` against a scenario. Never raises; problems go in ``error``."""
    try:
        scenario = load_scenario_text(scenario_text or default_scenario)
        if perturbed:
            scenario = apply_perturbation(scenario)
    except (ValueError, ValidationError, FileNotFoundError, yaml.YAMLError) as exc:
        return Result(error=f"scenario: {exc}", summary=f"ERROR: scenario: {exc}")

    try:
        output = parse_planner_output(plan_text)
    except (ValueError, ValidationError):
        output = None  # validate_raw turns the parse failure into a SCHEMA_INVALID violation

    if isinstance(output, Infeasible):
        agrees = not scenario.ground_truth.feasible
        verdict = "agrees" if agrees else "disagrees"
        return Result(
            declared_infeasible=True,
            agrees_with_ground_truth=agrees,
            summary=f"Scenario {scenario.id}: plan declares infeasible ({output.reason}); "
            f"ground truth {verdict}",
        )

    if output is None:
        report = validate_raw(scenario, plan_text, config)
    else:
        report = validate(scenario, output, config)
    return Result(
        valid=report.valid,
        violation_codes=[v.code.value for v in report.violations],
        summary=report.summary(),
        report_json=report.model_dump_json(),
    )
