"""Aggregate benchmark metrics per planner."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from statistics import mean

from pydantic import BaseModel, Field

from fleet_plan_bench.bench.runner import EpisodeResult


class PlannerMetrics(BaseModel):
    planner: str
    episodes: int
    feasible_episodes: int
    infeasible_episodes: int
    first_attempt_feasibility: float | None
    """Share of feasible episodes solved by a valid plan on the first attempt."""
    post_repair_feasibility: float | None
    """Share of feasible episodes ending with a valid plan after repairs."""
    repair_success: float | None
    """Of feasible episodes whose first attempt was invalid, the share fixed by repair."""
    mean_attempts: float
    hallucinated_reference_rate: float | None
    """Share of returned plans (all attempts) that reference unknown ids or do not parse."""
    infeasibility_precision: float | None
    infeasibility_recall: float | None
    false_infeasible: int
    """Feasible episodes the planner declared infeasible."""
    makespan_gap_vs_reference: float | None
    """Mean (makespan - reference) / reference over episodes with a valid final plan."""
    violations_first_attempt: dict[str, int] = Field(default_factory=dict)
    violations_all_attempts: dict[str, int] = Field(default_factory=dict)
    mean_input_tokens: float | None = None
    mean_output_tokens: float | None = None
    mean_latency_s: float | None = None
    by_tier: dict[str, dict[str, float | None]] = Field(default_factory=dict)


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _mean(xs: Sequence[float | int | None]) -> float | None:
    vals = [float(x) for x in xs if x is not None]
    return mean(vals) if vals else None


def compute_metrics(episodes: Sequence[EpisodeResult]) -> list[PlannerMetrics]:
    planners = list(dict.fromkeys(e.planner for e in episodes))
    return [_for_planner(p, [e for e in episodes if e.planner == p]) for p in planners]


def _for_planner(planner: str, eps: list[EpisodeResult]) -> PlannerMetrics:
    feas = [e for e in eps if e.ground_truth_feasible]
    infeas = [e for e in eps if not e.ground_truth_feasible]
    first_ok = [e for e in feas if e.first.outcome == "valid_plan"]
    final_ok = [e for e in feas if e.final.outcome == "valid_plan"]
    first_bad = [e for e in feas if e.first.outcome in ("invalid_plan", "error")]
    repaired = [e for e in first_bad if e.final.outcome == "valid_plan"]
    plan_attempts = [
        a for e in eps for a in e.attempts if a.outcome in ("valid_plan", "invalid_plan", "error")
    ]
    declared = [e for e in eps if e.final.outcome == "declared_infeasible"]
    tp = sum(not e.ground_truth_feasible for e in declared)
    gaps = [
        (e.final.makespan - e.reference_makespan) / e.reference_makespan
        for e in eps
        if e.final.outcome == "valid_plan" and e.final.makespan is not None and e.reference_makespan
    ]
    first_v: Counter[str] = Counter()
    all_v: Counter[str] = Counter()
    for e in eps:
        first_v.update(e.first.violations)
        for a in e.attempts:
            all_v.update(a.violations)
    attempts = [a for e in eps for a in e.attempts]
    by_tier: dict[str, dict[str, float | None]] = {}
    for tier in ("easy", "medium", "hard"):
        tf = [e for e in feas if e.tier == tier]
        ti = [e for e in infeas if e.tier == tier]
        by_tier[tier] = {
            "first_attempt_feasibility": _ratio(
                sum(e.first.outcome == "valid_plan" for e in tf), len(tf)
            ),
            "post_repair_feasibility": _ratio(
                sum(e.final.outcome == "valid_plan" for e in tf), len(tf)
            ),
            "infeasibility_recall": _ratio(
                sum(e.final.outcome == "declared_infeasible" for e in ti), len(ti)
            ),
        }
    return PlannerMetrics(
        planner=planner,
        episodes=len(eps),
        feasible_episodes=len(feas),
        infeasible_episodes=len(infeas),
        first_attempt_feasibility=_ratio(len(first_ok), len(feas)),
        post_repair_feasibility=_ratio(len(final_ok), len(feas)),
        repair_success=_ratio(len(repaired), len(first_bad)),
        mean_attempts=mean(len(e.attempts) for e in eps) if eps else 0.0,
        hallucinated_reference_rate=_ratio(
            sum(a.hallucinated for a in plan_attempts), len(plan_attempts)
        ),
        infeasibility_precision=_ratio(tp, len(declared)),
        infeasibility_recall=_ratio(tp, len(infeas)),
        false_infeasible=len(declared) - tp,
        makespan_gap_vs_reference=_mean(gaps),
        violations_first_attempt=dict(sorted(first_v.items())),
        violations_all_attempts=dict(sorted(all_v.items())),
        mean_input_tokens=_mean([a.input_tokens for a in attempts]),
        mean_output_tokens=_mean([a.output_tokens for a in attempts]),
        mean_latency_s=_mean([a.latency_s for a in attempts]),
        by_tier=by_tier,
    )
