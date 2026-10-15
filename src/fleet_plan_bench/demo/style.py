"""Shared visual constants for the live demo (browser map and Gazebo)."""

from __future__ import annotations

import math

FAILURE_MARKER = "failure_marker"
HIDDEN_Z = -50.0

# Colour-blind-friendly categorical palette, in fleet order.
VEHICLE_COLORS = [
    (0.00, 0.45, 0.70),
    (0.90, 0.62, 0.00),
    (0.00, 0.62, 0.45),
    (0.80, 0.47, 0.65),
    (0.34, 0.71, 0.91),
    (0.84, 0.37, 0.00),
    (0.94, 0.89, 0.26),
    (0.40, 0.40, 0.40),
]


def vehicle_color(index: int) -> tuple[float, float, float]:
    return VEHICLE_COLORS[index % len(VEHICLE_COLORS)]


def hex_color(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def scale_for(positions: dict[str, tuple[float, float]]) -> float:
    """Metres per layout unit, so the closest two zones are about 8 m apart in 3-D."""
    pts = list(positions.values())
    dmin = min(
        (math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1 :] if math.dist(a, b) > 0),
        default=1.0,
    )
    return 8.0 / dmin
