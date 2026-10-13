# fleet-plan-bench

A deterministic validator and benchmark for fleet plans for heterogeneous field vehicles
(agriculture, construction, mining). Plans can come from an LLM or from any other planner.

Give it a **scenario** (fleet + site graph + mission) and a **plan**. The validator returns
pass/fail with **typed constraint violations** that name the machines, tasks and zones
involved. The benchmark runs planners over a set of synthetic scenarios, feeds violations
back for repair, and reports feasibility, hallucination, infeasibility detection, repair
success and plan quality.

- Pure Python 3.10+, no ROS dependency, planner-agnostic.
- Optional **ROS 2 wrapper** (Jazzy): a validator node with a `validate_plan` service, plus
  Docker images and a VS Code dev container. See [ros2/README.md](ros2/README.md).
- The validator is fully deterministic. **No LLM is ever used to judge a plan.**
- All scenarios are **synthetic**. Units are abstract, and no real site, vehicle or
  customer data is included.

## Quickstart

```bash
pip install -e ".[dev]"            # core + test tools
pip install -e ".[ortools]"        # optional: OR-Tools CP-SAT baseline
pip install -e ".[llm]"            # optional: Anthropic LLM planner adapter

fpb list-scenarios
fpb show m03_mine_bench
fpb show e01_orchard_mowing --reference > plan.json   # a known-good plan
fpb validate e01_orchard_mowing plan.json             # exit 0: PASS
fpb validate e01_orchard_mowing examples/e01_broken_plan.json
```

```text
Scenario e01_orchard_mowing: FAIL (3 violation(s))
  - [UNKNOWN_MACHINE] assignment for task mow_b uses unknown machine 'mower_3'
  - [EDGE_MISSING] route for mower_2/mow_d uses non-existent edge barn-block_d
  - [TRAVEL_TIME_INFEASIBLE] mower_1 leaves block_a at t=13 and needs 1 to reach block_c, arriving t=14, but task mow_c starts at t=13
```

Run the benchmark:

```bash
fpb bench -p greedy -p ortools --out results/          # writes results.json + results.md
export ANTHROPIC_API_KEY=...                            # only for the LLM planner
fpb bench -p llm --out results/                         # model: $FPB_LLM_MODEL or claude-opus-5-5
fpb bench -p llm:<model-id> --tier hard                 # pick the model explicitly
fpb plan h05_excavator_breakdown --perturbed -p ortools # replanning after a breakdown
```

From Python:

```python
from fleet_plan_bench.io import find_scenario, load_plan
from fleet_plan_bench.validator import validate

report = validate(find_scenario("m03_mine_bench"), load_plan("plan.json"))
print(report.valid, report.counts())
print(report.model_dump_json(indent=2))  # structured report
```

## Schema reference

Scenarios and plans are JSON or YAML, validated with pydantic v2. Unknown fields are
rejected. Units are abstract: travel time = distance / speed, energy use = distance x
energy_per_distance.

### Scenario

| Field | Description |
|---|---|
| `id`, `tier` (`easy`/`medium`/`hard`), `domain`, `description` | Metadata |
| `fleet[]` | Machines (below) |
| `site.zones[]` | `id`, `kind`, `no_go` (a zone that must never be entered) |
| `site.edges[]` | Undirected: `a`, `b`, `distance`, `no_go`, `single_lane` |
| `site.charging_stations[]` | Zone ids where machines can charge |
| `mission.tasks[]` | Tasks (below) |
| `ground_truth` | `feasible`, `reason` (if infeasible), `reference_plan` (if feasible) |
| `perturbation` | Optional mid-mission event (below) |

**Machine:** `id`, `type`, `capabilities[]`, `speed`, `payload_capacity`, `battery_capacity`,
`energy_per_distance`, `charge_rate`, `start_zone`, optional `available_from` (default 0)
and `initial_energy` (default: full).

**Task:** `id`, `required_capability`, `zone`, `duration`, `payload_demand`,
`precedence[]` (task ids that must end before this one starts), optional
`time_window: {earliest_start, latest_end}`.

**Perturbation** (`kind: machine_failure`): at `time`, `machine` fails. The
`completed_tasks` are dropped, and the surviving machines restart from `machine_states`
(`zone`, `available_from`, `energy`). It has its own `ground_truth`. The benchmark runs
the replanning scenario as an extra episode (`<id>@machine_failure`); on the CLI use
`--perturbed`.

### Plan

```json
{"kind": "plan",
 "assignments": [
   {"machine": "drill_rig_1", "task": "drill_a",
    "route": ["portal", "decline_1", "decline_2", "bench_a"],
    "charging_stops": [{"zone": "decline_2"}],
    "start": 87.8, "end": 117.8}]}
```

or `{"kind": "infeasible", "reason": "..."}`.

Execution semantics:

- A machine runs its assignments in order of `start`.
- `route` goes from the machine's current zone (its `start_zone`, or the zone of its
  previous task) to the task zone, inclusive. A one-element route means it is already there.
- The machine departs when its previous task ends, or at `available_from`. It travels,
  charges, and works from `start` to `end`. Waiting is allowed.
- A charging stop `{zone, amount?}` charges at that zone when the route passes it (in
  order). Without `amount` it charges to full. Charging time = energy added / charge_rate.

### Violation codes

| Check | Codes |
|---|---|
| 1. Schema and references (hallucination) | `SCHEMA_INVALID`, `UNKNOWN_MACHINE`, `UNKNOWN_TASK`, `UNKNOWN_ZONE` |
| 2. Completeness | `TASK_UNASSIGNED`, `TASK_DUPLICATED` |
| 3. Capability and payload | `CAPABILITY_MISSING`, `PAYLOAD_EXCEEDED` |
| 4. Energy (default reserve 10% of capacity after every edge) | `ENERGY_DEPLETED`, `RESERVE_VIOLATED`, `INVALID_CHARGING_STOP` |
| 5. Route | `EDGE_MISSING`, `NO_GO_ZONE`, `NO_GO_EDGE`, `ROUTE_START_MISMATCH`, `ROUTE_END_MISMATCH` |
| 6. Temporal | `PRECEDENCE_VIOLATED`, `TIME_WINDOW_VIOLATED`, `MACHINE_OVERLAP`, `TRAVEL_TIME_INFEASIBLE`, `DURATION_TOO_SHORT` |
| v0.2, experimental, opt-in (`--single-lane`) | `SINGLE_LANE_CONFLICT` |

Each violation has a `code`, a human-readable `message` (written so it can be fed back to
a planner), and `machine_ids`, `task_ids` and `zone_ids`. Assignments that reference
unknown machines or tasks are reported once and excluded from later checks, so one
hallucination does not cascade into unrelated errors.

## Scenarios

| Id | Tier | Domain | Ground truth | What it tests |
|---|---|---|---|---|
| e01_orchard_mowing | easy | agriculture | feasible | homogeneous mowers |
| e02_quarry_haul | easy | mining | feasible | homogeneous trucks, payload |
| e03_site_grading | easy | construction | feasible | grid site, one time window |
| e04_spray_without_sprayer | easy | agriculture | **infeasible** | missing capability |
| m01_mixed_farm | medium | agriculture | feasible | heterogeneous, no-go wetland, precedence |
| m02_construction_earthworks | medium | construction | feasible | dig then haul or compact, charging |
| m03_mine_bench | medium | mining | feasible | underground charging on a long decline |
| m04_vent_shaft_out_of_range | medium | mining | **infeasible** | target beyond battery range |
| m05_precast_overweight | medium | construction | **infeasible** | payload exceeds every truck |
| h01_harvest_chain | hard | agriculture | feasible | harvest, cart, store chains with windows |
| h02_single_lane_ramp | hard | mining | feasible | 4-step chains, single-lane ramp |
| h03_pour_deadline | hard | construction | **infeasible** | precedence chain cannot meet deadline |
| h04_flooded_drift | hard | mining | **infeasible** | only access is through no-go areas |
| h05_excavator_breakdown | hard | construction | feasible | **mid-mission machine failure** + replanning |

Feasible scenarios ship a reference plan that the validator accepts. Infeasible
scenarios have witness tests in `tests/test_scenarios.py`: an independent argument
(e.g. a lower bound on chain length) plus a natural attempt that the validator rejects.

### How to add a scenario

1. Copy a YAML file in `src/fleet_plan_bench/scenarios/<tier>/` and rename it. The file
   stem must equal `id`. Keep it synthetic: no real site maps, vehicle specs or customer
   data.
2. If it is feasible, add a `ground_truth.reference_plan`. You can generate a candidate
   with `fpb plan <file> -p ortools` and check it with `fpb validate`. If it is
   infeasible, set `feasible: false` and a `reason`, and add a witness test.
3. Run `pytest`. The catalogue tests check that every reference plan validates.

## Plugging in a planner

Any object with a `name` and a `plan` method works (a `typing.Protocol`):

```python
from fleet_plan_bench.planners import RepairFeedback
from fleet_plan_bench.schemas import Infeasible, Plan, Scenario


class MyPlanner:
    name = "my-planner"
    repairable = True  # False: the benchmark will not ask it to repair

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Plan | Infeasible:
        # feedback (on repair attempts): .attempt, .previous (Plan), .violations (typed)
        ...
```

Then run it:

```python
from fleet_plan_bench.bench import compute_metrics, markdown_table, run_benchmark
from fleet_plan_bench.io import load_builtin_scenarios

episodes = run_benchmark([MyPlanner()], load_builtin_scenarios(), max_repairs=3)
print(markdown_table(compute_metrics(episodes)))
```

To report cost, set `self.last_usage = Usage(input_tokens=..., output_tokens=...,
latency_s=...)` after each call. An exception raised from `plan` is scored as
`SCHEMA_INVALID` and counts as a hallucinated plan.

Built-in planners:

- **greedy**: topological task order, earliest-finish capable machine, shortest
  no-go-free paths, and a charging-station detour when the reserve would be broken.
- **ortools** (extra): CP-SAT assigns and sequences tasks exactly, with travel times,
  precedence and time windows, minimising makespan. Energy is relaxed in the model, so a
  CP-SAT infeasibility proof is sound. Charging detours are then inserted and the schedule
  re-timed.
- **llm** (extra): the Anthropic Messages API with JSON-schema structured output. The
  model gets the scenario *without* ground truth, plus its previous plan and the typed
  violations on repair. The model id comes from `LLMPlannerConfig.model`, `FPB_LLM_MODEL`,
  or `llm:<model-id>`. Credentials come only from the environment (`ANTHROPIC_API_KEY` or
  an `ant auth` profile). Server-side refusal fallbacks are on by default
  (`server_fallbacks=False` to disable), and the serving model is recorded per attempt.
  The output schema does not restrict ids to an enum, so hallucinated references stay
  measurable.

## Metrics

| Metric | Definition |
|---|---|
| First-attempt feasibility | Feasible episodes solved by a valid plan on attempt 1 |
| Post-repair feasibility | Feasible episodes ending in a valid plan after up to 3 repairs |
| Repair success | Of feasible episodes with an invalid first plan, the share fixed by repair |
| Violation breakdown | Counts by code, first attempt and all attempts (in results.json) |
| Hallucinated-reference rate | Returned plans with unknown ids or unparseable output |
| Infeasibility detection | Precision and recall of `Infeasible` declarations (positive class = infeasible) |
| Makespan gap | Mean (makespan - reference) / reference over valid final plans |
| Tokens, latency | Mean per attempt, when the planner reports them |

## Results

Baselines on v0.1.0 (14 scenarios + 1 replanning episode = 15 episodes per planner;
full table in [docs/baseline-results.md](docs/baseline-results.md)):

| Planner | First-attempt feasible | Post-repair feasible | Repair success | Hallucinated refs | Infeasible precision | Infeasible recall | Makespan gap vs ref | Mean tokens (in/out) | Mean latency |
|---|---|---|---|---|---|---|---|---|---|
| greedy | 100% | 100% | - | 0% | 100% | 100% | +0.0% | -/- | - |
| ortools | 100% | 100% | - | 0% | 100% | 100% | -14.5% | -/- | - |

The reference plans were produced by the greedy baseline, so greedy's 0% gap holds by
construction, and both baselines were developed alongside these scenarios. The baselines
show that the scenarios are solvable and that the infeasible ones are detectable. They
say nothing about how hard the suite is for an LLM. **No LLM results are included yet.**
Run `fpb bench -p llm` with your own API key to produce them.

## Related work

This project builds on ideas from the following work. No code was copied from any of them.

- G. Tang et al., *Verification-Gated Agentic Mission-State Governance for Intelligent
  Industrial Multi-Robot Systems*, arXiv:2606.31339, 2026. Agentic proposals are committed
  only after deterministic verification.
- J. Tso et al., *ConstraintBench: Benchmarking LLM Constraint Reasoning on Direct
  Optimization*, arXiv:2602.22465, 2026. LLMs produce solutions directly, and a
  deterministic verifier checks them.
- K. Liu et al., *COHERENT: Collaboration of Heterogeneous Multi-Robot System with Large
  Language Models*, arXiv:2409.15146, 2024. LLM task planning for heterogeneous robots
  with a feedback loop.
- C. Rivera et al., *FLEET: Formal Language-Grounded Scheduling for Heterogeneous Robot
  Teams*, arXiv:2510.07417, 2025. An LLM front-end with a MILP scheduling back-end.
- R. Gupta et al., *RobotFleet: An Open-Source Framework for Centralized Multi-Robot Task
  Planning*, arXiv:2510.10379, 2025. An LLM-based centralized fleet planning framework.
- M. A. Ferrag et al., *UAVBench: An Open Benchmark Dataset for Autonomous and Agentic AI
  UAV Systems via LLM-Generated Flight Scenarios*, arXiv:2511.11252, 2025. Structured
  scenario benchmark for UAV reasoning.

**What this project adds:**

- An open, pip-installable, **planner-agnostic** validator and benchmark with no robotics
  middleware dependency.
- **Field-style heterogeneous scenarios**: mixed fleets with capabilities, payloads,
  batteries, charging stations, no-go areas and precedence chains.
- **Deliberately infeasible scenarios**, so planners are scored on *detecting*
  infeasibility (precision and recall), not only on producing plans.
- A **repair-loop metric** driven by typed, machine-readable violations.

## LIMITATIONS

- **This validates plan-level logic only.** It does not model vehicle dynamics,
  kinematics, traction, slopes, localization, perception, communications, sensor faults,
  weather, or human presence. Travel is distance / constant speed on an abstract graph,
  and energy is linear in distance.
- **It is not a safety assessment.** A plan that passes can still fail on a real machine.
  Passing says nothing about real-world safety and must never be used as a safety gate
  for physical equipment.
- Scenarios are small, hand-written and synthetic. They are not calibrated against real
  operations, and the baselines were tuned alongside them.
- Charging is modelled as charge-to-a-level at a station on the route. Energy spent while
  working on a task is not modelled.
- Single-lane conflict checking (v0.2) is experimental and opt-in. It assumes machines
  leave as soon as their previous task ends.
- The greedy and OR-Tools baselines are reference points, not state-of-the-art solvers.
  OR-Tools re-timing after charging insertion can break time windows (the validator
  would report it).

## Roadmap (v0.2 design)

- **Single-lane space-time conflicts**: `Edge.single_lane` and per-edge traversal
  intervals already exist (`validator/conflicts.py`, `--single-lane`). Still to do:
  explicit departure times in plans so planners can wait for a lane, and a planner-side
  conflict model.
- **Mid-mission replanning**: `Perturbation` and `apply_perturbation` exist, with one
  machine-failure scenario. Next: more event types (blocked edge, new urgent task,
  battery degradation) and metrics on plan stability versus the pre-event plan.

## ROS 2 wrapper

`ros2/` holds two optional ROS 2 packages: `fleet_plan_validator_interfaces` (a
`ValidatePlan` service) and `fleet_plan_validator_ros` (the validator node and a launch
file). They import the pip core unchanged, so results match the benchmark exactly.

```bash
docker build -f docker/ros2.Dockerfile --target runtime -t fleet-plan-validator:jazzy .
docker run --rm -it --network host fleet-plan-validator:jazzy \
  ros2 launch fleet_plan_validator_ros validator.launch.py default_scenario:=m03_mine_bench
```

Details, the service definition, and native (non-Docker) build steps are in
[ros2/README.md](ros2/README.md).

## Development

```bash
pip install -e ".[dev,ortools,llm]"
ruff check . && ruff format --check . && pytest
mypy src
```

Or open the repo in the **dev container** (`.devcontainer/`, ROS 2 Jazzy + all tools). It
installs the package and builds the ROS 2 workspace on creation;
`scripts/ros2_build.sh --test` rebuilds and tests the ROS 2 packages. CI runs ruff and
pytest on Python 3.10 and 3.12, plus a Docker job that builds and tests the ROS 2 packages
on Jazzy.

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).
