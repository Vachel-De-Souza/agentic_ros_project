"""Load and dump scenarios and plans as JSON or YAML."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from fleet_plan_bench.schemas import Infeasible, Plan, PlannerOutput, Scenario

_OUTPUT_ADAPTER: TypeAdapter[Plan | Infeasible] = TypeAdapter(PlannerOutput)


def _read(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate(_read(Path(path)))


def load_plan(path: str | Path) -> Plan | Infeasible:
    return parse_planner_output(_read(Path(path)))


def parse_planner_output(data: Any) -> Plan | Infeasible:
    """Parse a dict (or JSON string) into a Plan or Infeasible. ``kind`` defaults to plan."""
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict) and "kind" not in data:
        data = {**data, "kind": "infeasible" if "reason" in data else "plan"}
    return _OUTPUT_ADAPTER.validate_python(data)


def dump_json(model: Plan | Infeasible | Scenario, path: str | Path) -> None:
    Path(path).write_text(model.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")


def builtin_scenario_paths() -> list[Path]:
    """Paths of the bundled scenarios, sorted by tier then id."""
    root = Path(str(resources.files("fleet_plan_bench") / "scenarios"))
    order = {"easy": 0, "medium": 1, "hard": 2}
    paths = [p for p in root.rglob("*") if p.suffix in {".yaml", ".yml", ".json"}]
    return sorted(paths, key=lambda p: (order.get(p.parent.name, 9), p.name))


def load_builtin_scenarios() -> list[Scenario]:
    return [load_scenario(p) for p in builtin_scenario_paths()]


def find_scenario(name_or_path: str) -> Scenario:
    """Load a scenario by file path or by bundled scenario id."""
    p = Path(name_or_path)
    if p.exists():
        return load_scenario(p)
    for path in builtin_scenario_paths():
        if path.stem == name_or_path:
            return load_scenario(path)
    raise FileNotFoundError(f"no scenario file or built-in scenario named {name_or_path!r}")
