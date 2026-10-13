from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fleet_plan_bench.cli import app

runner = CliRunner()
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_list_and_show() -> None:
    r = runner.invoke(app, ["list-scenarios"])
    assert r.exit_code == 0
    assert "h05_excavator_breakdown" in r.output and "+perturbation" in r.output
    r = runner.invoke(app, ["show", "m04_vent_shaft_out_of_range"])
    assert r.exit_code == 0 and "infeasible" in r.output
    r = runner.invoke(app, ["show", "m04_vent_shaft_out_of_range", "--reference"])
    assert r.exit_code == 1


def test_validate_reference_and_broken(tmp_path: Path) -> None:
    ref = runner.invoke(app, ["show", "e01_orchard_mowing", "--reference"])
    plan = tmp_path / "plan.json"
    plan.write_text(ref.output)
    r = runner.invoke(app, ["validate", "e01_orchard_mowing", str(plan)])
    assert r.exit_code == 0 and "PASS" in r.output

    broken = EXAMPLES / "e01_broken_plan.json"
    r = runner.invoke(app, ["validate", "e01_orchard_mowing", str(broken), "--json"])
    assert r.exit_code == 1
    codes = {v["code"] for v in json.loads(r.output)["violations"]}
    assert codes == {"UNKNOWN_MACHINE", "EDGE_MISSING", "TRAVEL_TIME_INFEASIBLE"}


def test_validate_infeasible_declaration(tmp_path: Path) -> None:
    decl = tmp_path / "decl.json"
    decl.write_text(json.dumps({"kind": "infeasible", "reason": "no sprayer"}))
    assert runner.invoke(app, ["validate", "e04_spray_without_sprayer", str(decl)]).exit_code == 0
    assert runner.invoke(app, ["validate", "e01_orchard_mowing", str(decl)]).exit_code == 1


def test_plan_and_perturbed(tmp_path: Path) -> None:
    out = tmp_path / "p.json"
    r = runner.invoke(
        app,
        ["plan", "h05_excavator_breakdown", "--perturbed", "--planner", "greedy", "-o", str(out)],
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["validate", "h05_excavator_breakdown", str(out), "--perturbed"])
    assert r.exit_code == 0, r.output


def test_bench_writes_outputs(tmp_path: Path) -> None:
    r = runner.invoke(
        app, ["bench", "-p", "greedy", "--tier", "easy", "--out", str(tmp_path / "res")]
    )
    assert r.exit_code == 0, r.output
    assert "| greedy |" in r.output
    data = json.loads((tmp_path / "res" / "results.json").read_text())
    assert len(data["episodes"]) == 4
    assert (tmp_path / "res" / "results.md").read_text().startswith("# fleet-plan-bench results")


def test_merge_combines_runs(tmp_path: Path) -> None:
    for tier in ("easy", "medium"):
        r = runner.invoke(app, ["bench", "--tier", tier, "--out", str(tmp_path / tier)])
        assert r.exit_code == 0, r.output
    files = [str(tmp_path / t / "results.json") for t in ("easy", "medium")]
    r = runner.invoke(app, ["merge", *files, "--out", str(tmp_path / "merged")])
    assert r.exit_code == 0, r.output
    data = json.loads((tmp_path / "merged" / "results.json").read_text())
    assert len(data["episodes"]) == 9
    assert data["metrics"][0]["episodes"] == 9
