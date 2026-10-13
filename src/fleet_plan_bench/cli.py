"""Command-line interface: ``fpb``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from fleet_plan_bench.bench import (
    compute_metrics,
    markdown_report,
    markdown_table,
    run_benchmark,
    write_results,
)
from fleet_plan_bench.io import find_scenario, load_builtin_scenarios, load_plan
from fleet_plan_bench.planners import get_planner
from fleet_plan_bench.schemas import Infeasible, Scenario, apply_perturbation
from fleet_plan_bench.validator import ValidatorConfig, validate

app = typer.Typer(
    help="Deterministic validator and benchmark for heterogeneous fleet plans.",
    no_args_is_help=True,
    add_completion=False,
)

ScenarioArg = Annotated[str, typer.Argument(help="Scenario file path or built-in scenario id.")]
PerturbedOpt = Annotated[
    bool, typer.Option("--perturbed", help="Use the scenario after its mid-mission perturbation.")
]


def _scenario(name: str, perturbed: bool) -> Scenario:
    s = find_scenario(name)
    return apply_perturbation(s) if perturbed else s


@app.command("validate")
def validate_cmd(
    scenario: ScenarioArg,
    plan: Annotated[Path, typer.Argument(help="Plan file (JSON or YAML).", exists=True)],
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    reserve: Annotated[float, typer.Option(help="Energy reserve fraction.")] = 0.10,
    single_lane: Annotated[
        bool, typer.Option("--single-lane", help="Enable the experimental conflict check.")
    ] = False,
    perturbed: PerturbedOpt = False,
) -> None:
    """Validate a plan. Exit code 0 if valid, 1 if not."""
    s = _scenario(scenario, perturbed)
    out = load_plan(plan)
    if isinstance(out, Infeasible):
        agrees = not s.ground_truth.feasible
        msg = f"Plan declares infeasible: {out.reason}\nGround truth: " + (
            "infeasible (agrees)" if agrees else "feasible (disagrees)"
        )
        typer.echo(json.dumps({"declared_infeasible": True, "agrees": agrees}) if as_json else msg)
        raise typer.Exit(0 if agrees else 1)
    report = validate(
        s, out, ValidatorConfig(reserve_fraction=reserve, check_single_lane=single_lane)
    )
    typer.echo(report.model_dump_json(indent=2) if as_json else report.summary())
    raise typer.Exit(0 if report.valid else 1)


@app.command("list-scenarios")
def list_scenarios() -> None:
    """List the bundled scenarios."""
    for s in load_builtin_scenarios():
        gt = "feasible" if s.is_feasible else "INFEASIBLE"
        extra = " +perturbation" if s.perturbation else ""
        typer.echo(f"{s.id:34} {s.tier:7} {s.domain:13} {gt:10}{extra}".rstrip())


@app.command("show")
def show(
    scenario: ScenarioArg,
    reference: Annotated[
        bool, typer.Option("--reference", help="Print the reference plan as JSON.")
    ] = False,
    perturbed: PerturbedOpt = False,
) -> None:
    """Describe a scenario, or print its reference plan."""
    s = _scenario(scenario, perturbed)
    if reference:
        ref = s.ground_truth.reference_plan
        if ref is None:
            typer.echo(f"{s.id} has no reference plan ({s.ground_truth.reason})", err=True)
            raise typer.Exit(1)
        typer.echo(ref.model_dump_json(indent=2, exclude_none=True))
        return
    typer.echo(f"{s.id} [{s.tier}, {s.domain}] {s.description}")
    typer.echo(f"  fleet: {', '.join(f'{m.id} ({m.type})' for m in s.fleet)}")
    chargers = s.site.charging_stations
    typer.echo(f"  zones: {len(s.site.zones)}, edges: {len(s.site.edges)}, chargers: {chargers}")
    typer.echo(f"  tasks: {', '.join(t.id for t in s.mission.tasks)}")
    gt = s.ground_truth
    typer.echo(f"  ground truth: {'feasible' if gt.feasible else 'infeasible: ' + str(gt.reason)}")


@app.command("plan")
def plan_cmd(
    scenario: ScenarioArg,
    planner: Annotated[
        str, typer.Option(help="greedy, ortools, llm[:model] or ollama:<model>.")
    ] = "greedy",
    out: Annotated[Path | None, typer.Option("-o", "--out", help="Write the plan here.")] = None,
    perturbed: PerturbedOpt = False,
) -> None:
    """Run one planner on one scenario and print (or save) its output."""
    s = _scenario(scenario, perturbed)
    result = get_planner(planner).plan(s)
    text = result.model_dump_json(indent=2, exclude_none=True)
    if out is None:
        typer.echo(text)
    else:
        out.write_text(text + "\n")
        typer.echo(f"wrote {out}")


@app.command("bench")
def bench(
    planner: Annotated[
        list[str],
        typer.Option(
            "--planner", "-p", help="Repeatable: greedy, ortools, llm[:model], ollama:<model>."
        ),
    ] = ["greedy"],  # noqa: B006 - typer needs a literal default
    scenario: Annotated[
        list[str] | None, typer.Option("--scenario", "-s", help="Repeatable; default: all.")
    ] = None,
    tier: Annotated[str | None, typer.Option(help="Only run this tier.")] = None,
    max_repairs: Annotated[int, typer.Option(help="Repair attempts after the first.")] = 3,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("results"),
) -> None:
    """Run planners over scenarios; write results.json and results.md."""
    scenarios = [find_scenario(n) for n in scenario] if scenario else load_builtin_scenarios()
    if tier:
        scenarios = [s for s in scenarios if s.tier == tier]
    planners = [get_planner(p) for p in planner]
    episodes = run_benchmark(planners, scenarios, max_repairs=max_repairs)
    metrics = compute_metrics(episodes)
    out.mkdir(parents=True, exist_ok=True)
    write_results(out / "results.json", episodes, metrics)
    (out / "results.md").write_text(markdown_report(episodes, metrics))
    typer.echo(markdown_table(metrics))
    typer.echo(f"\nwrote {out / 'results.json'} and {out / 'results.md'}")


if __name__ == "__main__":  # pragma: no cover
    app()
