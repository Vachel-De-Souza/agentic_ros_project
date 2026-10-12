"""Plan schema: what a planner returns."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChargingStop(_Strict):
    """Charge at ``zone`` while traversing the route.

    ``amount`` is the energy to add; ``None`` means charge to full. The amount is
    capped at the battery capacity. Stops are matched to route zones in order.
    """

    zone: str
    amount: float | None = Field(default=None, gt=0)


class Assignment(_Strict):
    """One task executed by one machine.

    ``route`` runs from the machine's position before this task (its start zone, or the
    zone of its previous task) to the task zone, inclusive. A single-element route means
    the machine is already there. The machine departs when its previous task ends (or at
    its ``available_from`` time), travels and charges, then works from ``start`` to ``end``.
    """

    machine: str
    task: str
    route: list[str] = Field(min_length=1)
    start: float
    end: float
    charging_stops: list[ChargingStop] = Field(default_factory=list)


class Plan(_Strict):
    kind: Literal["plan"] = "plan"
    assignments: list[Assignment]
    planner: str | None = None
    notes: str | None = None

    def makespan(self) -> float:
        return max((a.end for a in self.assignments), default=0.0)


class Infeasible(_Strict):
    """A planner's declaration that no feasible plan exists."""

    kind: Literal["infeasible"] = "infeasible"
    reason: str
    planner: str | None = None


PlannerOutput = Annotated[Plan | Infeasible, Field(discriminator="kind")]
