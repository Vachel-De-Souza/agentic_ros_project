"""Results JSON and markdown tables."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from fleet_plan_bench import __version__
from fleet_plan_bench.bench.metrics import PlannerMetrics
from fleet_plan_bench.bench.runner import EpisodeResult


def results_dict(
    episodes: Sequence[EpisodeResult], metrics: Sequence[PlannerMetrics]
) -> dict[str, object]:
    return {
        "fleet_plan_bench_version": __version__,
        "metrics": [m.model_dump(mode="json") for m in metrics],
        "episodes": [e.model_dump(mode="json") for e in episodes],
    }


def load_episodes(path: str | Path) -> list[EpisodeResult]:
    """Episodes from a results.json written by ``write_results``."""
    data = json.loads(Path(path).read_text())
    return [EpisodeResult.model_validate(e) for e in data["episodes"]]


def write_results(
    path: str | Path, episodes: Sequence[EpisodeResult], metrics: Sequence[PlannerMetrics]
) -> None:
    Path(path).write_text(json.dumps(results_dict(episodes, metrics), indent=2) + "\n")


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None, fmt: str = "{:.0f}") -> str:
    return "-" if x is None else fmt.format(x)


def _gap(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:+.1f}%"


def markdown_table(metrics: Sequence[PlannerMetrics]) -> str:
    head = (
        "| Planner | First-attempt feasible | Post-repair feasible | Repair success "
        "| Hallucinated refs | Infeasible precision | Infeasible recall "
        "| Makespan gap vs ref | Mean tokens (in/out) | Mean latency | Episodes (infra-failed) |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|"
    )
    rows = [
        f"| {m.planner} | {_pct(m.first_attempt_feasibility)} "
        f"| {_pct(m.post_repair_feasibility)} | {_pct(m.repair_success)} "
        f"| {_pct(m.hallucinated_reference_rate)} | {_pct(m.infeasibility_precision)} "
        f"| {_pct(m.infeasibility_recall)} | {_gap(m.makespan_gap_vs_reference)} "
        f"| {_num(m.mean_input_tokens)}/{_num(m.mean_output_tokens)} "
        f"| {_num(m.mean_latency_s, '{:.2f}s')} "
        f"| {m.episodes} ({m.infra_failed_episodes}) |"
        for m in metrics
    ]
    return "\n".join([head, *rows])


def markdown_episodes(episodes: Sequence[EpisodeResult]) -> str:
    head = (
        "| Planner | Scenario | Tier | Ground truth | Outcome | Attempts | Makespan | Ref "
        "| First-attempt violations |\n|---|---|---|---|---|---|---|---|---|"
    )
    rows = []
    for e in episodes:
        v = ", ".join(f"{k} x{n}" for k, n in e.first.violations.items()) or "-"
        rows.append(
            f"| {e.planner} | {e.scenario_id} | {e.tier} "
            f"| {'feasible' if e.ground_truth_feasible else 'infeasible'} "
            f"| {e.final.outcome} | {len(e.attempts)} | {_num(e.final.makespan, '{:g}')} "
            f"| {_num(e.reference_makespan, '{:g}')} | {v} |"
        )
    return "\n".join([head, *rows])


def markdown_report(episodes: Sequence[EpisodeResult], metrics: Sequence[PlannerMetrics]) -> str:
    parts = [
        f"# fleet-plan-bench results (v{__version__})",
        "",
        "## Summary",
        "",
        markdown_table(metrics),
        "",
        "Makespan gap is relative to each scenario's reference plan (produced by the greedy "
        "baseline). Infeasibility precision/recall treat *infeasible* as the positive class.",
        "",
        "## Episodes",
        "",
        markdown_episodes(episodes),
        "",
    ]
    return "\n".join(parts)
