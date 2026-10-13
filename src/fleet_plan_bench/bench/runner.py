"""Run planners over scenarios, with a validator-driven repair loop."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence

from pydantic import BaseModel, Field

from fleet_plan_bench.planners.base import Planner, PlannerUnavailableError, RepairFeedback
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
    """``valid_plan``, ``invalid_plan``, ``declared_infeasible``, ``error`` (planner output
    could not be used; scored) or ``infra_error`` (planner unreachable; not scored)."""
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

    @property
    def infra_failed(self) -> bool:
        """The episode was cut short by an unreachable planner; metrics exclude it."""
        return self.final.outcome == "infra_error"


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
    retries: int = 3,
    retry_backoff_s: float = 10.0,
    progress: Callable[[str], None] | None = None,
) -> EpisodeResult:
    """One planning episode: first attempt plus up to ``max_repairs`` repair attempts.

    A ``PlannerUnavailableError`` is retried ``retries`` times with exponential backoff;
    if it persists the attempt is recorded as ``infra_error`` and the episode stops.
    """
    attempts: list[AttemptRecord] = []
    feedback: RepairFeedback | None = None
    previous: Plan | Infeasible | None = None
    repairable = getattr(planner, "repairable", True)
    for k in range(max_repairs + 1):
        rec, output, violations = _attempt(
            planner, scenario, feedback, k, config, retries, retry_backoff_s
        )
        attempts.append(rec)
        if progress is not None:
            progress(_describe(planner.name, scenario.id, rec))
        if rec.outcome in ("valid_plan", "declared_infeasible", "infra_error"):
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
    retries: int = 3,
    retry_backoff_s: float = 10.0,
) -> tuple[AttemptRecord, Plan | Infeasible | None, list[Violation]]:
    try:
        output = _plan_with_retries(planner, scenario, feedback, retries, retry_backoff_s)
    except PlannerUnavailableError as exc:
        rec = AttemptRecord(
            attempt=k,
            outcome="infra_error",
            reason=str(exc)[:500],
            **_usage_fields(getattr(planner, "last_usage", None)),
        )
        return rec, None, []
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


def _plan_with_retries(
    planner: Planner,
    scenario: Scenario,
    feedback: RepairFeedback | None,
    retries: int,
    backoff_s: float,
) -> Plan | Infeasible:
    for i in range(retries + 1):
        try:
            return planner.plan(scenario, feedback)
        except PlannerUnavailableError:
            if i == retries:
                raise
            time.sleep(backoff_s * (2**i))
    raise AssertionError("unreachable")


def _describe(planner: str, scenario_id: str, rec: AttemptRecord) -> str:
    detail = ", ".join(f"{c} x{n}" for c, n in rec.violations.items()) or rec.reason or ""
    latency = f" {rec.latency_s:.1f}s" if rec.latency_s is not None else ""
    text = f"[{planner}] {scenario_id} attempt {rec.attempt}: {rec.outcome}{latency}"
    return f"{text} ({detail[:160]})" if detail else text


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
    retries: int = 3,
    retry_backoff_s: float = 10.0,
    progress: Callable[[str], None] | None = None,
) -> list[EpisodeResult]:
    items = expand_scenarios(scenarios)
    return [
        run_episode(
            p,
            s,
            perturbed=perturbed,
            max_repairs=max_repairs,
            config=config,
            retries=retries,
            retry_backoff_s=retry_backoff_s,
            progress=progress,
        )
        for p in planners
        for s, perturbed in items
    ]
