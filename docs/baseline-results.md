# fleet-plan-bench results (v0.1.0)

## Summary

| Planner | First-attempt feasible | Post-repair feasible | Repair success | Hallucinated refs | Infeasible precision | Infeasible recall | Makespan gap vs ref | Mean tokens (in/out) | Mean latency |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 100% | 100% | - | 0% | 100% | 100% | +0.0% | -/- | - |
| ortools | 100% | 100% | - | 0% | 100% | 100% | -14.5% | -/- | - |

Makespan gap is relative to each scenario's reference plan (produced by the greedy baseline). Infeasibility precision/recall treat *infeasible* as the positive class.

## Episodes

| Planner | Scenario | Tier | Ground truth | Outcome | Attempts | Makespan | Ref | First-attempt violations |
|---|---|---|---|---|---|---|---|---|
| greedy | e01_orchard_mowing | easy | feasible | valid_plan | 1 | 25.5 | 25.5 | - |
| greedy | e02_quarry_haul | easy | feasible | valid_plan | 1 | 23 | 23 | - |
| greedy | e03_site_grading | easy | feasible | valid_plan | 1 | 56.668 | 56.668 | - |
| greedy | e04_spray_without_sprayer | easy | infeasible | declared_infeasible | 1 | - | - | - |
| greedy | m01_mixed_farm | medium | feasible | valid_plan | 1 | 75 | 75 | - |
| greedy | m02_construction_earthworks | medium | feasible | valid_plan | 1 | 110.2 | 110.2 | - |
| greedy | m03_mine_bench | medium | feasible | valid_plan | 1 | 207.8 | 207.8 | - |
| greedy | m04_vent_shaft_out_of_range | medium | infeasible | declared_infeasible | 1 | - | - | - |
| greedy | m05_precast_overweight | medium | infeasible | declared_infeasible | 1 | - | - | - |
| greedy | h01_harvest_chain | hard | feasible | valid_plan | 1 | 118.72 | 118.72 | - |
| greedy | h02_single_lane_ramp | hard | feasible | valid_plan | 1 | 207.12 | 207.12 | - |
| greedy | h03_pour_deadline | hard | infeasible | declared_infeasible | 1 | - | - | - |
| greedy | h04_flooded_drift | hard | infeasible | declared_infeasible | 1 | - | - | - |
| greedy | h05_excavator_breakdown | hard | feasible | valid_plan | 1 | 104.2 | 104.2 | - |
| greedy | h05_excavator_breakdown@machine_failure | hard | feasible | valid_plan | 1 | 170.2 | 170.2 | - |
| ortools | e01_orchard_mowing | easy | feasible | valid_plan | 1 | 25.5 | 25.5 | - |
| ortools | e02_quarry_haul | easy | feasible | valid_plan | 1 | 23 | 23 | - |
| ortools | e03_site_grading | easy | feasible | valid_plan | 1 | 44.334 | 56.668 | - |
| ortools | e04_spray_without_sprayer | easy | infeasible | declared_infeasible | 1 | - | - | - |
| ortools | m01_mixed_farm | medium | feasible | valid_plan | 1 | 68 | 75 | - |
| ortools | m02_construction_earthworks | medium | feasible | valid_plan | 1 | 93 | 110.2 | - |
| ortools | m03_mine_bench | medium | feasible | valid_plan | 1 | 207.8 | 207.8 | - |
| ortools | m04_vent_shaft_out_of_range | medium | infeasible | declared_infeasible | 1 | - | - | - |
| ortools | m05_precast_overweight | medium | infeasible | declared_infeasible | 1 | - | - | - |
| ortools | h01_harvest_chain | hard | feasible | valid_plan | 1 | 98.667 | 118.72 | - |
| ortools | h02_single_lane_ramp | hard | feasible | valid_plan | 1 | 138 | 207.12 | - |
| ortools | h03_pour_deadline | hard | infeasible | declared_infeasible | 1 | - | - | - |
| ortools | h04_flooded_drift | hard | infeasible | declared_infeasible | 1 | - | - | - |
| ortools | h05_excavator_breakdown | hard | feasible | valid_plan | 1 | 78 | 104.2 | - |
| ortools | h05_excavator_breakdown@machine_failure | hard | feasible | valid_plan | 1 | 131 | 170.2 | - |
