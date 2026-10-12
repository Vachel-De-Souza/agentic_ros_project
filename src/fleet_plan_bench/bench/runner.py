"""Run planners over scenarios, with a validator-driven repair loop."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from fleet_plan_bench.planners.base import Planner, RepairFeedback
from fleet_plan_bench.schemas import (
    Infeasible,
    Plan,
    Scenario,
    Violation,
    ViolationCode,
    apply_perturbation,
)
from fleet_plan_bench.validator import ValidatorConfig, validate


class AttemptRecord(BaseModel):
    attempt: int
    outcome: str
    """``valid_plan``, ``invalid_plan``, ``declared_infeasible`` or ``error``."""
    violations: dict[str, int] = Field(default_factory=dict)
    hallucinated: bool = False
    makespan: float | None = None
    reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_s: float | None = None


class EpisodeResult(BaseModel):
    planner: str
    scenario_id: str
    tier: str
    domain: str
    perturbed: bool
    ground_truth_feasible: bool
    reference_makespan: float | None
    attempts: list[AttemptRecord]

    @property
    def first(self) -> AttemptRecord:
        return self.attempts[0]

    @property
    def final(self) -> AttemptRecord:
        return self.attempts[-1]


def expand_scenarios(scenarios: Iterable[Scenario]) -> list[tuple[Scenario, bool]]:
    """Each scenario, plus its post-perturbation replanning scenario when it has one."""
    out: list[tuple[Scenario, bool]] = []
    for s in scenarios:
        out.append((s, False))
        if s.perturbation is not None:
            out.append((apply_perturbation(s), True))
    return out


def run_episode(
    planner: Planner,
    scenario: Scenario,
    *,
    perturbed: bool = False,
    max_repairs: int = 3,
    config: ValidatorConfig | None = None,
) -> EpisodeResult:
    """One planning episode: first attempt plus up to ``max_repairs`` repair attempts."""
    attempts: list[AttemptRecord] = []
    feedback: RepairFeedback | None = None
    previous: Plan | Infeasible | None = None
    repairable = getattr(planner, "repairable", True)
    for k in range(max_repairs + 1):
        rec, output, violations = _attempt(planner, scenario, feedback, k, config)
        attempts.append(rec)
        if rec.outcome in ("valid_plan", "declared_infeasible"):
            break
        if not repairable or (output is not None and output == previous):
            break
        previous = output
        plan_for_feedback = output if isinstance(output, Plan) else Plan(assignments=[])
        feedback = RepairFeedback(attempt=k + 1, previous=plan_for_feedback, violations=violations)
    ref = scenario.ground_truth.reference_plan
    return EpisodeResult(
        planner=planner.name,
        scenario_id=scenario.id,
        tier=scenario.tier,
        domain=scenario.domain,
        perturbed=perturbed,
        ground_truth_feasible=scenario.ground_truth.feasible,
        reference_makespan=ref.makespan() if ref is not None else None,
        attempts=attempts,
    )


def _attempt(
    planner: Planner,
    scenario: Scenario,
    feedback: RepairFeedback | None,
    k: int,
    config: ValidatorConfig | None,
) -> tuple[AttemptRecord, Plan | Infeasible | None, list[Violation]]:
    try:
        output = planner.plan(scenario, feedback)
    except Exception as exc:  # a planner crash or unparseable LLM output is scored, not fatal
        usage = getattr(planner, "last_usage", None)
        v = Violation(code=ViolationCode.SCHEMA_INVALID, message=f"planner output error: {exc}")
        rec = AttemptRecord(
            attempt=k,
            outcome="error",
            violations={v.code.value: 1},
            hallucinated=True,
            reason=str(exc)[:500],
            **_usage_fields(usage),
        )
        return rec, None, [v]
    usage = getattr(planner, "last_usage", None)
    if isinstance(output, Infeasible):
        rec = AttemptRecord(
            attempt=k, outcome="declared_infeasible", reason=output.reason, **_usage_fields(usage)
        )
        return rec, output, []
    report = validate(scenario, output, config)
    rec = AttemptRecord(
        attempt=k,
        outcome="valid_plan" if report.valid else "invalid_plan",
        violations=report.counts(),
        hallucinated=report.has_hallucination,
        makespan=report.makespan,
        **_usage_fields(usage),
    )
    return rec, output, report.violations


def _usage_fields(usage: object) -> dict[str, float | int | None]:
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "latency_s": getattr(usage, "latency_s", None),
    }


def run_benchmark(
    planners: Sequence[Planner],
    scenarios: Iterable[Scenario],
    *,
    max_repairs: int = 3,
    config: ValidatorConfig | None = None,
) -> list[EpisodeResult]:
    items = expand_scenarios(scenarios)
    return [
        run_episode(p, s, perturbed=perturbed, max_repairs=max_repairs, config=config)
        for p in planners
        for s, perturbed in items
    ]
