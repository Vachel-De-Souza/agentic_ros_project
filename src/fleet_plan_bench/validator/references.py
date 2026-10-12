"""Check 1: reference integrity. Unknown IDs are hallucinations."""

from __future__ import annotations

from fleet_plan_bench.schemas import Violation, ViolationCode
from fleet_plan_bench.validator.context import Context


def check_references(ctx: Context) -> list[Violation]:
    out: list[Violation] = []
    for a in ctx.plan.assignments:
        if a.machine not in ctx.machines:
            out.append(
                Violation(
                    code=ViolationCode.UNKNOWN_MACHINE,
                    message=f"assignment for task {a.task} uses unknown machine {a.machine!r}",
                    machine_ids=[a.machine],
                    task_ids=[a.task],
                )
            )
        if a.task not in ctx.tasks:
            out.append(
                Violation(
                    code=ViolationCode.UNKNOWN_TASK,
                    message=f"machine {a.machine} is assigned unknown task {a.task!r}",
                    machine_ids=[a.machine],
                    task_ids=[a.task],
                )
            )
        zones = [*a.route, *(s.zone for s in a.charging_stops)]
        for z in dict.fromkeys(zones):
            if z not in ctx.graph.zones:
                out.append(
                    Violation(
                        code=ViolationCode.UNKNOWN_ZONE,
                        message=f"assignment {a.machine}/{a.task} references unknown zone {z!r}",
                        machine_ids=[a.machine],
                        task_ids=[a.task],
                        zone_ids=[z],
                    )
                )
    return out
