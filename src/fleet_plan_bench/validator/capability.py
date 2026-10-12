"""Check 3: capability and payload limits."""

from __future__ import annotations

from fleet_plan_bench.schemas import Violation, ViolationCode
from fleet_plan_bench.validator.context import Context


def check_capability(ctx: Context) -> list[Violation]:
    out: list[Violation] = []
    for _, a in ctx.resolved:
        m, t = ctx.machines[a.machine], ctx.tasks[a.task]
        if t.required_capability not in m.capabilities:
            out.append(
                Violation(
                    code=ViolationCode.CAPABILITY_MISSING,
                    message=(
                        f"{m.id} ({m.type}, capabilities {m.capabilities}) cannot do task {t.id}, "
                        f"which requires {t.required_capability!r}"
                    ),
                    machine_ids=[m.id],
                    task_ids=[t.id],
                )
            )
        if t.payload_demand > m.payload_capacity + ctx.config.tolerance:
            out.append(
                Violation(
                    code=ViolationCode.PAYLOAD_EXCEEDED,
                    message=(
                        f"task {t.id} needs payload {t.payload_demand:g} but {m.id} carries at "
                        f"most {m.payload_capacity:g}"
                    ),
                    machine_ids=[m.id],
                    task_ids=[t.id],
                )
            )
    return out
