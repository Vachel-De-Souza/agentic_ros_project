# fleet-plan-bench results (v0.1.0)

## Summary

| Planner | First-attempt feasible | Post-repair feasible | Repair success | Hallucinated refs | Infeasible precision | Infeasible recall | Makespan gap vs ref | Mean tokens (in/out) | Mean latency | Episodes (infra-failed) |
|---|---|---|---|---|---|---|---|---|---|---|
| greedy | 100% | 100% | - | 0% | 100% | 100% | +0.0% | -/- | - | 15 (0) |
| ortools | 100% | 100% | - | 0% | 100% | 100% | -14.5% | -/- | - | 15 (0) |
| ollama:gemma4:12b | 40% | 90% | 83% | 0% | 100% | 100% | -6.1% | 2213/343 | 91.44s | 15 (0) |
| ollama:qwen3.5:9b | 0% | 20% | 25% | 0% | 50% | 100% | +73.3% | 2188/439 | 72.62s | 15 (0) |

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
| ollama:gemma4:12b | e01_orchard_mowing | easy | feasible | valid_plan | 1 | 25.5 | 25.5 | - |
| ollama:gemma4:12b | e02_quarry_haul | easy | feasible | valid_plan | 1 | 23 | 23 | - |
| ollama:gemma4:12b | e03_site_grading | easy | feasible | valid_plan | 1 | 47.3333 | 56.668 | - |
| ollama:gemma4:12b | e04_spray_without_sprayer | easy | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:gemma4:12b | m01_mixed_farm | medium | feasible | valid_plan | 1 | 74 | 75 | - |
| ollama:gemma4:12b | m02_construction_earthworks | medium | feasible | valid_plan | 2 | 122 | 110.2 | TRAVEL_TIME_INFEASIBLE x2 |
| ollama:gemma4:12b | m03_mine_bench | medium | feasible | valid_plan | 3 | 225 | 207.8 | ENERGY_DEPLETED x1, TRAVEL_TIME_INFEASIBLE x2 |
| ollama:gemma4:12b | m04_vent_shaft_out_of_range | medium | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:gemma4:12b | m05_precast_overweight | medium | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:gemma4:12b | h01_harvest_chain | hard | feasible | invalid_plan | 3 | - | 118.72 | RESERVE_VIOLATED x1, TRAVEL_TIME_INFEASIBLE x4 |
| ollama:gemma4:12b | h02_single_lane_ramp | hard | feasible | valid_plan | 2 | 164 | 207.12 | TRAVEL_TIME_INFEASIBLE x1 |
| ollama:gemma4:12b | h03_pour_deadline | hard | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:gemma4:12b | h04_flooded_drift | hard | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:gemma4:12b | h05_excavator_breakdown | hard | feasible | valid_plan | 3 | 91 | 104.2 | EDGE_MISSING x1, TRAVEL_TIME_INFEASIBLE x2 |
| ollama:gemma4:12b | h05_excavator_breakdown@machine_failure | hard | feasible | valid_plan | 2 | 131 | 170.2 | EDGE_MISSING x3, TRAVEL_TIME_INFEASIBLE x2 |
| ollama:qwen3.5:9b | e01_orchard_mowing | easy | feasible | valid_plan | 4 | 62 | 25.5 | TASK_DUPLICATED x1, TRAVEL_TIME_INFEASIBLE x5 |
| ollama:qwen3.5:9b | e02_quarry_haul | easy | feasible | invalid_plan | 4 | - | 23 | EDGE_MISSING x1, TRAVEL_TIME_INFEASIBLE x4 |
| ollama:qwen3.5:9b | e03_site_grading | easy | feasible | invalid_plan | 4 | - | 56.668 | TRAVEL_TIME_INFEASIBLE x5 |
| ollama:qwen3.5:9b | e04_spray_without_sprayer | easy | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:qwen3.5:9b | m01_mixed_farm | medium | feasible | invalid_plan | 4 | - | 75 | ROUTE_END_MISMATCH x1, TASK_UNASSIGNED x1, TRAVEL_TIME_INFEASIBLE x2 |
| ollama:qwen3.5:9b | m02_construction_earthworks | medium | feasible | valid_plan | 4 | 114 | 110.2 | ROUTE_START_MISMATCH x1, TRAVEL_TIME_INFEASIBLE x3 |
| ollama:qwen3.5:9b | m03_mine_bench | medium | feasible | declared_infeasible | 2 | - | 207.8 | EDGE_MISSING x2, ENERGY_DEPLETED x2, PRECEDENCE_VIOLATED x1, RESERVE_VIOLATED x1, TRAVEL_TIME_INFEASIBLE x4 |
| ollama:qwen3.5:9b | m04_vent_shaft_out_of_range | medium | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:qwen3.5:9b | m05_precast_overweight | medium | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:qwen3.5:9b | h01_harvest_chain | hard | feasible | declared_infeasible | 2 | - | 118.72 | EDGE_MISSING x1, MACHINE_OVERLAP x4, NO_GO_ZONE x1, ROUTE_START_MISMATCH x4, TIME_WINDOW_VIOLATED x1, TRAVEL_TIME_INFEASIBLE x2 |
| ollama:qwen3.5:9b | h02_single_lane_ramp | hard | feasible | declared_infeasible | 3 | - | 207.12 | EDGE_MISSING x4, MACHINE_OVERLAP x1, PRECEDENCE_VIOLATED x2, ROUTE_START_MISMATCH x2, TRAVEL_TIME_INFEASIBLE x4 |
| ollama:qwen3.5:9b | h03_pour_deadline | hard | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:qwen3.5:9b | h04_flooded_drift | hard | infeasible | declared_infeasible | 1 | - | - | - |
| ollama:qwen3.5:9b | h05_excavator_breakdown | hard | feasible | declared_infeasible | 1 | - | 104.2 | - |
| ollama:qwen3.5:9b | h05_excavator_breakdown@machine_failure | hard | feasible | declared_infeasible | 1 | - | 170.2 | - |
