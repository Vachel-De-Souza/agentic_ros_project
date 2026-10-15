"""Mid-mission machine failure against an *executing* plan (not a pre-written snapshot).

``split_at_failure`` decides, from the plan being executed, which work is already done or
committed at time ``t``, where every surviving machine will be and with how much energy,
and returns the remaining replanning scenario plus the committed assignments.

Rules:
- The failed machine keeps only assignments it finished by ``t``; its other tasks go back
  to the pool.
- A surviving machine finishes any assignment it has already set off on (departed before
  ``t``), but only if every predecessor of that task is itself committed. Otherwise that
  assignment and the machine's later ones are cancelled (repeated until stable). A
  cancelled machine stays at the zone it was at, or at the task zone if it already arrived.
- Remaining tasks whose predecessors are committed get an earliest start at the
  predecessor's end. Nothing new may start before ``t``.
"""

from __future__ import annotations

from fleet_plan_bench.schemas import (
    Assignment,
    GroundTruth,
    Mission,
    Plan,
    Scenario,
    TimeWindow,
)
from fleet_plan_bench.validator import ValidatorConfig
from fleet_plan_bench.validator.context import Context, Leg


def split_at_failure(
    scenario: Scenario,
    plan: Plan,
    machine_id: str,
    t: float,
    config: ValidatorConfig | None = None,
) -> tuple[Scenario, list[Assignment]]:
    if machine_id not in {m.id for m in scenario.fleet}:
        raise ValueError(f"unknown machine {machine_id!r}")
    ctx = Context.build(scenario, plan, config or ValidatorConfig())
    preds = {task.id: set(task.precedence) for task in scenario.mission.tasks}
    # candidate prefixes of each machine's legs
    kept: dict[str, list[Leg]] = {}
    for m in scenario.fleet:
        legs = []
        for leg in ctx.legs.get(m.id, []):
            a = leg.assignment
            if not (a.end <= t if m.id == machine_id else (leg.depart < t or a.end <= t)):
                break
            legs.append(leg)
        kept[m.id] = legs
    # drop legs whose predecessors are not committed, cutting the machine's prefix there
    changed = True
    while changed:
        changed = False
        done = {leg.assignment.task for legs in kept.values() for leg in legs}
        for m_id, legs in kept.items():
            for k, leg in enumerate(legs):
                if not preds.get(leg.assignment.task, set()) <= done:
                    kept[m_id] = legs[:k]
                    changed = True
                    break
    committed: list[Assignment] = []
    end_of: dict[str, float] = {}
    fleet = []
    for m in scenario.fleet:
        zone, ready, energy = m.start_zone, max(t, m.available_from), m.start_energy
        for leg in kept[m.id]:
            committed.append(leg.assignment)
            end_of[leg.assignment.task] = leg.assignment.end
            zone, ready, energy = leg.task.zone, max(t, leg.assignment.end), leg.energy_end
        if m.id == machine_id:
            continue
        legs_all = ctx.legs.get(m.id, [])
        if len(kept[m.id]) < len(legs_all):  # a cancelled leg may already be under way
            nxt = legs_all[len(kept[m.id])]
            if nxt.depart < t and nxt.arrival <= t:
                zone = nxt.task.zone
                energy = nxt.energy_end
        fleet.append(
            m.model_copy(
                update={"start_zone": zone, "available_from": ready, "initial_energy": energy}
            )
        )
    tasks = []
    for task in scenario.mission.tasks:
        if task.id in end_of:
            continue
        earliest = max(
            [end_of[p] for p in task.precedence if p in end_of]
            + [task.time_window.earliest_start if task.time_window else 0.0]
        )
        window = task.time_window or TimeWindow()
        if earliest > window.earliest_start:
            window = window.model_copy(update={"earliest_start": earliest})
        tasks.append(
            task.model_copy(
                update={
                    "precedence": [p for p in task.precedence if p not in end_of],
                    "time_window": window if task.time_window or earliest > 0 else None,
                }
            )
        )
    remaining = Scenario(
        id=f"{scenario.id}@failure:{machine_id}@{t:g}",
        tier=scenario.tier,
        domain=scenario.domain,
        description=f"{scenario.description} [{machine_id} failed at t={t:g}; ground truth "
        "unknown: this replanning scenario was generated at run time]",
        fleet=fleet,
        site=scenario.site,
        mission=Mission(tasks=tasks),
        ground_truth=GroundTruth(feasible=True),
    )
    return remaining, committed


def merge(committed: list[Assignment], replan: Plan) -> Plan:
    """The plan actually executed: committed work plus the replanned remainder."""
    return Plan(assignments=[*committed, *replan.assignments], planner=replan.planner)
