"""Check 4: energy along routes, with reserve margin and charging stops."""

from __future__ import annotations

from fleet_plan_bench.schemas import Violation
from fleet_plan_bench.validator.context import Context


def check_energy(ctx: Context) -> list[Violation]:
    legs = sorted((leg for ls in ctx.legs.values() for leg in ls), key=lambda leg: leg.index)
    return [v for leg in legs for v in leg.energy_violations]
