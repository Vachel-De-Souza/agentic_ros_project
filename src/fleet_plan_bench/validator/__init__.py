"""Deterministic plan validator. No LLM is involved in judging a plan."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from fleet_plan_bench.io import parse_planner_output
from fleet_plan_bench.schemas import Plan, Scenario, ValidationReport, Violation, ViolationCode
from fleet_plan_bench.validator.capability import check_capability
from fleet_plan_bench.validator.completeness import check_completeness
from fleet_plan_bench.validator.conflicts import check_single_lane
from fleet_plan_bench.validator.context import Context, ValidatorConfig
from fleet_plan_bench.validator.energy import check_energy
from fleet_plan_bench.validator.references import check_references
from fleet_plan_bench.validator.routes import check_routes
from fleet_plan_bench.validator.temporal import check_temporal

__all__ = ["ValidatorConfig", "validate", "validate_raw"]

CHECKS = (
    check_references,
    check_completeness,
    check_capability,
    check_energy,
    check_routes,
    check_temporal,
)


def validate(
    scenario: Scenario, plan: Plan, config: ValidatorConfig | None = None
) -> ValidationReport:
    """Validate ``plan`` against ``scenario``. Pure function of its inputs."""
    config = config or ValidatorConfig()
    ctx = Context.build(scenario, plan, config)
    violations = [v for check in CHECKS for v in check(ctx)]
    if config.check_single_lane:
        violations += check_single_lane(ctx)
    valid = not violations
    return ValidationReport(
        scenario_id=scenario.id,
        valid=valid,
        violations=violations,
        makespan=plan.makespan() if valid else None,
    )


def validate_raw(
    scenario: Scenario, data: Any, config: ValidatorConfig | None = None
) -> ValidationReport:
    """Validate an unparsed plan (dict or JSON string); schema errors become violations."""
    try:
        out = parse_planner_output(data)
    except (ValidationError, ValueError) as exc:
        return ValidationReport(
            scenario_id=scenario.id,
            valid=False,
            violations=[
                Violation(code=ViolationCode.SCHEMA_INVALID, message=f"plan does not parse: {exc}")
            ],
        )
    if not isinstance(out, Plan):
        raise TypeError("validate_raw expects a plan, got an Infeasible declaration")
    return validate(scenario, out, config)
