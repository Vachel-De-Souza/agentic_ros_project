"""``fpb-sim-world``: write the Gazebo world and GUI config for a scenario."""

from __future__ import annotations

import argparse
from pathlib import Path

from fleet_plan_bench.io import find_scenario
from fleet_plan_bench.layout import layout
from fleet_plan_sim.world import build_world, gui_config


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenario", help="scenario file or built-in id")
    ap.add_argument("--out-dir", default=".", help="where to write world.sdf and gui.config")
    args = ap.parse_args(argv)
    scenario = find_scenario(args.scenario)
    pos = layout(scenario.site)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "world.sdf").write_text(build_world(scenario, pos))
    (out / "gui.config").write_text(gui_config(pos))
    print(f"wrote {out / 'world.sdf'} and {out / 'gui.config'}")


if __name__ == "__main__":
    main()
