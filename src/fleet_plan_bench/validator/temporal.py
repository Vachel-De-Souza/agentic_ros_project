"""Check 6: precedence, time windows, durations, travel time and per-machine non-overlap."""

from __future__ import annotations

from fleet_plan_bench.schemas import Violation, ViolationCode
from fleet_plan_bench.validator.context import Context


def check_temporal(ctx: Context) -> list[Violation]:
    tol = ctx.config.tolerance
    out: list[Violation] = []
    for m_id, legs in ctx.legs.items():
        for k, leg in enumerate(legs):
            a, task = leg.assignment, leg.task
            prev = legs[k - 1].assignment if k else None
            if prev is not None and a.start < prev.end - tol:
                out.append(
                    Violation(
                        code=ViolationCode.MACHINE_OVERLAP,
                        message=(
                            f"{m_id} works on {prev.task} until t={prev.end:g} but starts "
                            f"{a.task} at t={a.start:g}"
                        ),
                        machine_ids=[m_id],
                        task_ids=[prev.task, a.task],
                    )
                )
            elif a.start < leg.arrival - tol:
                extra = f" incl. {leg.charge_time:g} charging" if leg.charge_time else ""
                out.append(
                    Violation(
                        code=ViolationCode.TRAVEL_TIME_INFEASIBLE,
                        message=(
                            f"{m_id} leaves {leg.origin} at t={leg.depart:g} and needs "
                            f"{leg.arrival - leg.depart:g}{extra} to reach {task.zone}, arriving "
                            f"t={leg.arrival:g}, but task {a.task} starts at t={a.start:g}"
                        ),
                        machine_ids=[m_id],
                        task_ids=[a.task],
                        zone_ids=[task.zone],
                    )
                )
            if a.end - a.start < task.duration - tol:
                out.append(
                    Violation(
                        code=ViolationCode.DURATION_TOO_SHORT,
                        message=(
                            f"task {a.task} needs duration {task.duration:g} but is scheduled "
                            f"for {a.end - a.start:g} (t={a.start:g}..{a.end:g})"
                        ),
                        machine_ids=[m_id],
                        task_ids=[a.task],
                    )
                )
            tw = task.time_window
            if tw is not None and (
                a.start < tw.earliest_start - tol or a.end > tw.latest_end + tol
            ):
                out.append(
                    Violation(
                        code=ViolationCode.TIME_WINDOW_VIOLATED,
                        message=(
                            f"task {a.task} runs t={a.start:g}..{a.end:g} outside its window "
                            f"[{tw.earliest_start:g}, {tw.latest_end:g}]"
                        ),
                        machine_ids=[m_id],
                        task_ids=[a.task],
                    )
                )
    for task in ctx.scenario.mission.tasks:
        cur = ctx.first_assignment(task.id)
        if cur is None:
            continue
        for pred_id in task.precedence:
            p = ctx.first_assignment(pred_id)
            if p is not None and cur.start < p.end - tol:
                out.append(
                    Violation(
                        code=ViolationCode.PRECEDENCE_VIOLATED,
                        message=(
                            f"task {task.id} starts at t={cur.start:g} before its predecessor "
                            f"{pred_id} ends at t={p.end:g}"
                        ),
                        machine_ids=sorted({cur.machine, p.machine}),
                        task_ids=[pred_id, task.id],
                    )
                )
    return out
