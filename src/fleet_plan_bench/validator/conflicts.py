"""v0.2 (experimental, opt-in): single-lane space-time conflicts.

Assumes eager departure: each machine leaves as soon as its previous task ends and
traverses its route without waiting. Two different machines may not occupy the same
single-lane edge during overlapping time intervals, in either direction.
"""

from __future__ import annotations

from fleet_plan_bench.schemas import Violation, ViolationCode
from fleet_plan_bench.validator.context import Context, EdgeTraversal


def check_single_lane(ctx: Context) -> list[Violation]:
    tol = ctx.config.tolerance
    by_edge: dict[frozenset[str], list[tuple[str, str, EdgeTraversal]]] = {}
    for m_id, legs in ctx.legs.items():
        for leg in legs:
            for tr in leg.traversals:
                by_edge.setdefault(frozenset((tr.a, tr.b)), []).append(
                    (m_id, leg.assignment.task, tr)
                )
    out: list[Violation] = []
    for items in by_edge.values():
        items.sort(key=lambda it: (it[2].t0, it[0]))
        for i, (m1, t1, a) in enumerate(items):
            for m2, t2, b in items[i + 1 :]:
                if m1 != m2 and a.t0 < b.t1 - tol and b.t0 < a.t1 - tol:
                    out.append(
                        Violation(
                            code=ViolationCode.SINGLE_LANE_CONFLICT,
                            message=(
                                f"{m1} ({a.a}->{a.b}, t={a.t0:g}..{a.t1:g}) and {m2} "
                                f"({b.a}->{b.b}, t={b.t0:g}..{b.t1:g}) share single-lane edge "
                                f"{a.a}-{a.b}"
                            ),
                            machine_ids=[m1, m2],
                            task_ids=[t1, t2],
                            zone_ids=sorted({a.a, a.b}),
                        )
                    )
    return out
