"""ROS-free test for the Gazebo world generator (phase 2 preview)."""

from __future__ import annotations

import xml.dom.minidom

from fleet_plan_sim.world import build_world, gui_config

from fleet_plan_bench.demo.style import FAILURE_MARKER
from fleet_plan_bench.io import find_scenario
from fleet_plan_bench.layout import layout


def test_world_and_gui_config_are_valid_xml() -> None:
    s = find_scenario("h05_excavator_breakdown")
    world = build_world(s)
    dom = xml.dom.minidom.parseString(world)
    names = {m.getAttribute("name") for m in dom.getElementsByTagName("model")}
    assert {m.id for m in s.fleet} <= names
    assert FAILURE_MARKER in names
    assert {f"zone_{z.id}" for z in s.site.zones} <= names
    assert "gz::sim::systems::Physics" in world  # needed for set_pose to take effect
    gui = gui_config(layout(s.site))
    xml.dom.minidom.parseString("<root>" + gui.split("?>", 1)[1] + "</root>")
