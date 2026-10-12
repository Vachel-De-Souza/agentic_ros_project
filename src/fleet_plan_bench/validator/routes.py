"""Check 5: route validity (edges exist, no-go zones and edges avoided, endpoints right)."""

from __future__ import annotations

from itertools import pairwise

from fleet_plan_bench.schemas import Violation, ViolationCode
from fleet_plan_bench.validator.context import Context


def check_routes(ctx: Context) -> list[Violation]:
    out: list[Violation] = []
    g = ctx.graph
    legs = sorted((leg for ls in ctx.legs.values() for leg in ls), key=lambda leg: leg.index)
    for leg in legs:
        a, task = leg.assignment, leg.task
        refs = {"machine_ids": [a.machine], "task_ids": [a.task]}
        if a.route[0] != leg.origin:
            out.append(
                Violation(
                    code=ViolationCode.ROUTE_START_MISMATCH,
                    message=(
                        f"route for {a.machine}/{a.task} starts at {a.route[0]} but the machine "
                        f"is at {leg.origin}"
                    ),
                    zone_ids=[a.route[0], leg.origin],
                    **refs,
                )
            )
        if a.route[-1] != task.zone:
            out.append(
                Violation(
                    code=ViolationCode.ROUTE_END_MISMATCH,
                    message=(
                        f"route for {a.machine}/{a.task} ends at {a.route[-1]} but task "
                        f"{task.id} is at {task.zone}"
                    ),
                    zone_ids=[a.route[-1], task.zone],
                    **refs,
                )
            )
        for x, y in pairwise(a.route):
            if x == y or x not in g.zones or y not in g.zones:
                continue
            edge = g.edge(x, y)
            if edge is None:
                out.append(
                    Violation(
                        code=ViolationCode.EDGE_MISSING,
                        message=f"route for {a.machine}/{a.task} uses non-existent edge {x}-{y}",
                        zone_ids=[x, y],
                        **refs,
                    )
                )
            elif edge.no_go:
                out.append(
                    Violation(
                        code=ViolationCode.NO_GO_EDGE,
                        message=f"route for {a.machine}/{a.task} uses no-go edge {x}-{y}",
                        zone_ids=[x, y],
                        **refs,
                    )
                )
        for z in dict.fromkeys(a.route[1:]):
            if z in g.zones and g.zones[z].no_go:
                out.append(
                    Violation(
                        code=ViolationCode.NO_GO_ZONE,
                        message=f"route for {a.machine}/{a.task} enters no-go zone {z}",
                        zone_ids=[z],
                        **refs,
                    )
                )
    return out
