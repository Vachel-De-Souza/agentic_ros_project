"""Check 2: every task is assigned exactly once."""

from __future__ import annotations

from collections import Counter

from fleet_plan_bench.schemas import Violation, ViolationCode
from fleet_plan_bench.validator.context import Context


def check_completeness(ctx: Context) -> list[Violation]:
    counts = Counter(a.task for a in ctx.plan.assignments)
    out: list[Violation] = []
    for t in ctx.scenario.mission.tasks:
        n = counts.get(t.id, 0)
        if n == 0:
            out.append(
                Violation(
                    code=ViolationCode.TASK_UNASSIGNED,
                    message=f"task {t.id} ({t.required_capability} at {t.zone}) is not assigned",
                    task_ids=[t.id],
                )
            )
        elif n > 1:
            machines = sorted({a.machine for a in ctx.plan.assignments if a.task == t.id})
            out.append(
                Violation(
                    code=ViolationCode.TASK_DUPLICATED,
                    message=f"task {t.id} is assigned {n} times (machines {machines})",
                    task_ids=[t.id],
                    machine_ids=machines,
                )
            )
    return out
