"""Build a Gazebo (SDF) world from a scenario: zones, roads, chargers, vehicles."""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from fleet_plan_bench.demo.style import FAILURE_MARKER, HIDDEN_Z, scale_for, vehicle_color
from fleet_plan_bench.layout import layout
from fleet_plan_bench.schemas import Scenario

WORLD_NAME = "fleet_demo"

ZONE_COLORS = {
    "depot": (0.55, 0.55, 0.60),
    "field": (0.45, 0.70, 0.35),
    "orchard": (0.35, 0.60, 0.30),
    "storage": (0.75, 0.65, 0.45),
    "stockpile": (0.65, 0.55, 0.45),
    "pit": (0.55, 0.45, 0.40),
    "bench": (0.60, 0.55, 0.50),
    "work_area": (0.80, 0.72, 0.50),
}
DEFAULT_ZONE = (0.72, 0.72, 0.68)
NO_GO = (0.85, 0.15, 0.15)
ROAD = (0.30, 0.30, 0.32)
SINGLE_LANE = (0.95, 0.55, 0.10)


def _material(rgb: tuple[float, float, float], alpha: float = 1.0) -> str:
    c = f"{rgb[0]} {rgb[1]} {rgb[2]} {alpha}"
    return f"<material><ambient>{c}</ambient><diffuse>{c}</diffuse></material>"


def _static_box(name: str, x: float, y: float, z: float, yaw: float, size: str, mat: str) -> str:
    return (
        f'<model name="{escape(name)}"><static>true</static>'
        f"<pose>{x:.3f} {y:.3f} {z:.3f} 0 0 {yaw:.4f}</pose>"
        f'<link name="link"><visual name="visual"><geometry><box><size>{size}</size></box>'
        f"</geometry>{mat}</visual></link></model>"
    )


def _cylinder(name: str, x: float, y: float, z: float, r: float, h: float, mat: str) -> str:
    return (
        f'<model name="{escape(name)}"><static>true</static>'
        f"<pose>{x:.3f} {y:.3f} {z:.3f} 0 0 0</pose>"
        f'<link name="link"><visual name="visual"><geometry><cylinder><radius>{r:.3f}</radius>'
        f"<length>{h:.3f}</length></cylinder></geometry>{mat}</visual></link></model>"
    )


def build_world(scenario: Scenario, positions: dict[str, tuple[float, float]] | None = None) -> str:
    pos = positions or layout(scenario.site)
    k = scale_for(pos)
    xy = {z: (p[0] * k, p[1] * k) for z, p in pos.items()}
    zones = {z.id: z for z in scenario.site.zones}
    parts: list[str] = []
    for e in scenario.site.edges:
        (xa, ya), (xb, yb) = xy[e.a], xy[e.b]
        length = math.hypot(xb - xa, yb - ya)
        color = NO_GO if e.no_go else SINGLE_LANE if e.single_lane else ROAD
        width = 0.8 if e.single_lane else 1.4
        parts.append(
            _static_box(
                f"road_{e.a}_{e.b}",
                (xa + xb) / 2,
                (ya + yb) / 2,
                0.02,
                math.atan2(yb - ya, xb - xa),
                f"{length:.3f} {width} 0.04",
                _material(color),
            )
        )
    for z_id, (x, y) in xy.items():
        z = zones[z_id]
        color = NO_GO if z.no_go else ZONE_COLORS.get(z.kind, DEFAULT_ZONE)
        parts.append(_cylinder(f"zone_{z_id}", x, y, 0.05, 3.0, 0.1, _material(color)))
        if z_id in scenario.site.charging_stations:
            charger = _material((1.0, 0.85, 0.1))
            parts.append(
                _static_box(f"charger_{z_id}", x + 2.2, y + 2.2, 0.75, 0, "0.6 0.6 1.5", charger)
            )
    for i, m in enumerate(scenario.fleet):
        x, y = xy[m.start_zone]
        parts.append(_static_box(m.id, x, y, 0.6, 0, "2.4 1.4 1.0", _material(vehicle_color(i))))
    parts.append(_cylinder(FAILURE_MARKER, 0, 0, HIDDEN_Z, 0.5, 3.0, _material(NO_GO)))
    xs = [p[0] for p in xy.values()]
    ys = [p[1] for p in xy.values()]
    size = max(max(xs) - min(xs), max(ys) - min(ys)) + 30
    ground = (
        '<model name="ground"><static>true</static><link name="link"><visual name="visual">'
        f"<geometry><plane><normal>0 0 1</normal><size>{size:.1f} {size:.1f}</size></plane>"
        f"</geometry>{_material((0.62, 0.66, 0.55))}</visual></link></model>"
    )
    return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <world name="{WORLD_NAME}">
    <!-- generated from scenario {escape(scenario.id)}; synthetic, abstract units -->
    <!-- Physics applies the poses requested through set_pose (UserCommands) -->
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <scene><ambient>0.6 0.6 0.6 1</ambient><background>0.78 0.85 0.92 1</background>
      <shadows>false</shadows></scene>
    <light type="directional" name="sun"><cast_shadows>false</cast_shadows>
      <pose>0 0 30 0 0 0</pose><diffuse>0.9 0.9 0.9 1</diffuse>
      <direction>-0.3 0.2 -1</direction></light>
    {ground}
    {"".join(parts)}
  </world>
</sdf>
"""


def camera_pose(positions: dict[str, tuple[float, float]]) -> str:
    """An oblique bird's-eye camera pose (x y z roll pitch yaw) covering the whole site."""
    k = scale_for(positions)
    xs = [p[0] * k for p in positions.values()]
    ys = [p[1] * k for p in positions.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), 20)
    return f"{cx:.2f} {cy - 0.75 * span:.2f} {0.95 * span:.2f} 0 0.9 1.5708"


def gui_config(positions: dict[str, tuple[float, float]]) -> str:
    """A minimal Gazebo GUI: just the 3D view, camera framing the whole site."""
    floating = (
        '<gz-gui><property key="state" type="string">floating</property>'
        '<property key="width" type="double">5</property>'
        '<property key="height" type="double">5</property>'
        '<property key="showTitleBar" type="bool">false</property></gz-gui>'
    )
    helpers = "".join(
        f'<plugin filename="{f}" name="{n}">{floating}</plugin>'
        for f, n in [
            ("GzSceneManager", "Scene Manager"),
            ("InteractiveViewControl", "Interactive view control"),
            ("CameraTracking", "Camera Tracking"),
            ("EntityContextMenuPlugin", "Entity context menu"),
        ]
    )
    return f"""<?xml version="1.0"?>
<window><position_x>0</position_x><position_y>0</position_y>
  <width>1280</width><height>800</height>
  <menus><drawer default="false"/></menus><dialog_on_exit>false</dialog_on_exit></window>
<plugin filename="MinimalScene" name="3D View">
  <gz-gui><title>3D View</title><property type="bool" key="showTitleBar">false</property>
    <property type="string" key="state">docked</property></gz-gui>
  <engine>ogre2</engine><scene>scene</scene>
  <ambient_light>0.5 0.5 0.5</ambient_light>
  <background_color>0.78 0.85 0.92 1</background_color>
  <camera_pose>{camera_pose(positions)}</camera_pose>
</plugin>
{helpers}
"""
