"""2-D positions for site zones, for visualisation only (the validator never uses them).

Zones with ``pos`` keep it. The others are placed by deterministic stress majorization so
straight-line distances roughly match shortest-path road distances.
"""

from __future__ import annotations

import math

from fleet_plan_bench.schemas import Site


def _all_pairs(site: Site) -> dict[tuple[str, str], float]:
    """Floyd-Warshall over every edge (no-go included: this is about geometry)."""
    ids = [z.id for z in site.zones]
    inf = float("inf")
    d = {(a, b): (0.0 if a == b else inf) for a in ids for b in ids}
    for e in site.edges:
        d[(e.a, e.b)] = d[(e.b, e.a)] = min(d[(e.a, e.b)], e.distance)
    for k in ids:
        for i in ids:
            dik = d[(i, k)]
            if dik == inf:
                continue
            for j in ids:
                if dik + d[(k, j)] < d[(i, j)]:
                    d[(i, j)] = dik + d[(k, j)]
    finite = [v for v in d.values() if v != inf]
    far = 1.5 * max(finite, default=1.0)
    return {k: (far if v == inf else v) for k, v in d.items()}


def layout(site: Site, iterations: int = 300) -> dict[str, tuple[float, float]]:
    ids = [z.id for z in site.zones]
    fixed = {z.id: z.pos for z in site.zones if z.pos is not None}
    if len(fixed) == len(ids):
        return {k: (float(v[0]), float(v[1])) for k, v in fixed.items()}
    d = _all_pairs(site)
    radius = max(d.values()) / 2 or 1.0
    pos: dict[str, list[float]] = {}
    for k, z in enumerate(ids):
        if z in fixed:
            pos[z] = [float(fixed[z][0]), float(fixed[z][1])]
        else:
            angle = 2 * math.pi * k / len(ids)
            pos[z] = [radius * math.cos(angle), radius * math.sin(angle)]
    for _ in range(iterations):
        for i in ids:
            if i in fixed:
                continue
            nx = ny = wsum = 0.0
            for j in ids:
                if i == j or d[(i, j)] == 0:
                    continue
                dij = d[(i, j)]
                w = dij**-2
                dx, dy = pos[i][0] - pos[j][0], pos[i][1] - pos[j][1]
                norm = math.hypot(dx, dy) or 1e-9
                nx += w * (pos[j][0] + dij * dx / norm)
                ny += w * (pos[j][1] + dij * dy / norm)
                wsum += w
            if wsum:
                pos[i] = [nx / wsum, ny / wsum]
    if not fixed:  # centre on the origin for a free layout
        cx = sum(p[0] for p in pos.values()) / len(pos)
        cy = sum(p[1] for p in pos.values()) / len(pos)
        pos = {k: [p[0] - cx, p[1] - cy] for k, p in pos.items()}
    return {k: (round(p[0], 3), round(p[1], 3)) for k, p in pos.items()}
