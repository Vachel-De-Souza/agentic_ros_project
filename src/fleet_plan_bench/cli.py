"""Command-line interface: ``fpb``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from fleet_plan_bench.bench import (
    compute_metrics,
    load_episodes,
    markdown_report,
    markdown_table,
    run_benchmark,
    write_results,
)
from fleet_plan_bench.io import find_scenario, load_builtin_scenarios, load_plan
from fleet_plan_bench.planners import Planner, get_planner
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
    episodes = run_benchmark(
        planners,
        scenarios,
        max_repairs=max_repairs,
        progress=lambda line: typer.echo(line, err=True),
    )
    metrics = compute_metrics(episodes)
    out.mkdir(parents=True, exist_ok=True)
    write_results(out / "results.json", episodes, metrics)
    (out / "results.md").write_text(markdown_report(episodes, metrics))
    typer.echo(markdown_table(metrics))
    typer.echo(f"\nwrote {out / 'results.json'} and {out / 'results.md'}")


@app.command("demo")
def demo(
    scenario: Annotated[
        str, typer.Argument(help="Scenario file or built-in id.")
    ] = "h05_excavator_breakdown",
    planner: Annotated[
        str | None,
        typer.Option(
            "--planner",
            "-p",
            help="Default: $FPB_DEMO_PLANNER, else ollama:gemma4:12b if "
            "FPB_OLLAMA_URL is set, else ortools.",
        ),
    ] = None,
    fallback: Annotated[
        str, typer.Option(help="Used if the planner gives no valid plan ('none' to disable).")
    ] = "ortools",
    failure: Annotated[
        str, typer.Option(help="'scenario' (its own breakdown), 'none', or 'machine@time'.")
    ] = "scenario",
    seconds: Annotated[float, typer.Option(help="Wall-clock length of the playback.")] = 60.0,
    port: Annotated[int, typer.Option(help="Dashboard port.")] = 8080,
    host: Annotated[str, typer.Option(help="Bind address ('0.0.0.0' to share).")] = "127.0.0.1",
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = True,
    autostart: Annotated[bool, typer.Option(help="Start the mission immediately.")] = False,
) -> None:
    """Live browser demo: plan, validate, repair, play back, break down, replan."""
    import os
    import threading
    import time
    import webbrowser

    from fleet_plan_bench.demo import Dashboard, DemoConfig, DemoRunner, NullMover

    s = find_scenario(scenario)
    if failure == "none":
        s = s.model_copy(update={"perturbation": None})
    name = (
        planner
        or os.environ.get("FPB_DEMO_PLANNER")
        or ("ollama:gemma4:12b" if os.environ.get("FPB_OLLAMA_URL") else "ortools")
    )
    config = DemoConfig(
        mission_seconds=seconds,
        failure=_parse_failure(failure),
        fallback=_planner_or_greedy(fallback) if fallback != "none" else None,
    )
    runner = DemoRunner(s, _planner_or_greedy(name), NullMover(), config)
    thread: threading.Thread | None = None

    def start() -> None:
        nonlocal thread
        if thread is None or not thread.is_alive():
            thread = threading.Thread(target=runner.run, daemon=True)
            thread.start()

    dash = Dashboard(runner.snapshot, start, host=host, port=port, view="map")
    dash.start()
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{dash.port}/"
    typer.echo(f"Live demo for {s.id} with planner {runner.planner.name}: {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    if autostart:
        start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dash.stop()


def _parse_failure(value: str) -> tuple[str, float] | None:
    if value in ("", "scenario", "none"):
        return None
    machine, _, t = value.partition("@")
    return machine, float(t)


def _planner_or_greedy(name: str) -> Planner:
    """OR-Tools is an optional extra; fall back to greedy if it is not installed."""
    try:
        return get_planner(name)
    except ImportError:
        typer.echo(f"{name} is not installed; using greedy instead", err=True)
        return get_planner("greedy")


@app.command("merge")
def merge(
    results: Annotated[
        list[Path], typer.Argument(help="results.json files from separate runs.", exists=True)
    ],
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("results/merged"),
) -> None:
    """Merge results.json files (e.g. one per model) into one report."""
    episodes = [e for path in results for e in load_episodes(path)]
    metrics = compute_metrics(episodes)
    out.mkdir(parents=True, exist_ok=True)
    write_results(out / "results.json", episodes, metrics)
    (out / "results.md").write_text(markdown_report(episodes, metrics))
    typer.echo(markdown_table(metrics))
    typer.echo(f"\nwrote {out / 'results.json'} and {out / 'results.md'}")


if __name__ == "__main__":  # pragma: no cover
    app()
