"""Live demo (browser, phase 1): runner state machine and dashboard."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from fleet_plan_bench.demo import Dashboard, DemoConfig, DemoRunner
from fleet_plan_bench.demo.style import FAILURE_MARKER
from fleet_plan_bench.io import find_scenario
from fleet_plan_bench.planners import GreedyPlanner, RepairFeedback
from fleet_plan_bench.schemas import Plan, Scenario

SCENARIO = "h05_excavator_breakdown"


class FakeMover:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, float, float, float, float]] = []

    def set_pose(
        self, name: str, x: float, y: float, z: float, yaw: float, roll: float = 0.0
    ) -> None:
        self.calls.append((name, x, y, z, yaw, roll))


class SloppyThenGreedy:
    """First attempt of each planning round is broken; repairs use the greedy plan."""

    name = "scripted-ai"
    repairable = True
    last_usage = None

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Any:
        good = GreedyPlanner().plan(scenario)
        assert isinstance(good, Plan)
        if feedback is None:
            bad = good.model_copy(deep=True)
            bad.assignments[0].start = bad.assignments[0].end  # zero duration
            return bad
        return good


def test_runner_full_story_with_repair_failure_and_replan() -> None:
    s = find_scenario(SCENARIO)
    mover = FakeMover()
    runner = DemoRunner(
        s, SloppyThenGreedy(), mover, DemoConfig(mission_seconds=0.5), sleep=lambda _: None
    )
    runner.run()
    st = runner.snapshot()
    assert st["phase"] == "done"
    rounds = [(a["round"], a["outcome"]) for a in st["attempts"]]
    assert rounds == [
        ("initial", "rejected"),
        ("initial", "valid"),
        ("replan", "rejected"),
        ("replan", "valid"),
    ]
    assert any("DURATION_TOO_SHORT" in d for d in st["attempts"][0]["details"])
    assert st["machines"]["excavator_1"]["status"] == "failed"
    assert all(m["status"] == "done" for k, m in st["machines"].items() if k != "excavator_1")
    assert st["summary"]["rejected"] == 2
    # the failure marker was raised above the failed vehicle, which was tilted
    assert any(c[0] == FAILURE_MARKER and c[3] > 0 for c in mover.calls)
    assert any(c[0] == "excavator_1" and c[5] != 0 for c in mover.calls)


def test_runner_stops_when_no_valid_plan() -> None:
    s = find_scenario("e04_spray_without_sprayer")
    runner = DemoRunner(s, GreedyPlanner(), FakeMover(), sleep=lambda _: None)
    runner.run()
    st = runner.snapshot()
    assert st["phase"] == "failed"
    assert st["attempts"][0]["outcome"] == "declared_infeasible"


def test_dashboard_serves_page_state_and_start() -> None:
    started: list[bool] = []
    dash = Dashboard(lambda: {"phase": "ready"}, lambda: started.append(True), port=0)
    dash.start()
    try:
        base = f"http://127.0.0.1:{dash.port}"
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "Fleet plan live demo" in page
        assert "__NOVNC_PORT__" not in page and 'const VIEW = "map"' in page
        assert json.loads(urllib.request.urlopen(base + "/state").read()) == {"phase": "ready"}
        urllib.request.urlopen(urllib.request.Request(base + "/start", method="POST"))
        assert started == [True]
    finally:
        dash.stop()


def test_browser_state_has_map_positions_for_every_vehicle() -> None:
    s = find_scenario(SCENARIO)
    runner = DemoRunner(s, GreedyPlanner(), FakeMover(), DemoConfig(mission_seconds=0.2),
                        sleep=lambda _: None)  # fmt: skip
    st = runner.snapshot()
    assert {z["id"] for z in st["scenario"]["zones"]} == {z.id for z in s.site.zones}
    assert all("pos" in z for z in st["scenario"]["zones"])
    positions = {(round(m["x"], 3), round(m["y"], 3)) for m in st["machines"].values()}
    assert len(positions) == len(s.fleet)  # parked vehicles are offset, not stacked


def test_fpb_demo_command_serves_dashboard(monkeypatch: Any) -> None:
    """`fpb demo` starts the dashboard on the requested port and exits on Ctrl+C."""
    import time

    from typer.testing import CliRunner

    from fleet_plan_bench import cli
    from fleet_plan_bench.demo import dashboard as dash_mod

    served: dict[str, bytes] = {}
    original_start = dash_mod.Dashboard.start

    def capture_start(self: Any) -> None:
        original_start(self)
        served["page"] = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/").read()

    def interrupt(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(dash_mod.Dashboard, "start", capture_start)
    monkeypatch.setattr(time, "sleep", interrupt)
    monkeypatch.delenv("FPB_DEMO_PLANNER", raising=False)
    monkeypatch.delenv("FPB_OLLAMA_URL", raising=False)
    result = CliRunner().invoke(cli.app, ["demo", "e01_orchard_mowing", "--no-open", "--port", "0"])
    assert result.exit_code == 0, result.output
    assert "planner ortools" in result.output or "planner greedy" in result.output
    assert b"Fleet plan live demo" in served["page"]
