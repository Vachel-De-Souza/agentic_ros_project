# ROS 2 wrapper

Two optional ROS 2 packages that expose the deterministic fleet-plan-bench validator to a
ROS 2 system. A typical use is a mission planner node that calls the validator before
dispatch. The core package stays pure Python with no ROS dependency; these packages only
adapt it.

| Package | Build type | Contents |
|---|---|---|
| `fleet_plan_validator_interfaces` | ament_cmake | `srv/ValidatePlan.srv` |
| `fleet_plan_validator_ros` | ament_python | `validator_node` + `validator.launch.py` |

Tested on **ROS 2 Jazzy** (Ubuntu 24.04, Python 3.12). Humble (Python 3.10) should work with
`--build-arg ROS_DISTRO=humble`, but it is not tested in CI.

## Interfaces

Node name `fleet_plan_validator`:

| Kind | Name | Type |
|---|---|---|
| Service | `/fleet_plan_validator/validate_plan` | `fleet_plan_validator_interfaces/srv/ValidatePlan` |
| Subscription | `/fleet_plan_validator/plan` | `std_msgs/msg/String` (plan JSON) |
| Publisher | `/fleet_plan_validator/report` | `std_msgs/msg/String` (result JSON) |

The topic pair validates against the `default_scenario` parameter.

| Parameter | Default | Meaning |
|---|---|---|
| `default_scenario` | `""` | Built-in scenario id, file path, or JSON/YAML text, used when a request has none |
| `reserve_fraction` | `0.1` | Energy reserve as a fraction of battery capacity |
| `check_single_lane` | `false` | Experimental single-lane conflict check |

**Request:** `scenario` (JSON/YAML text, a built-in id, or empty for the default), `plan`
(JSON), `perturbed` (validate the post-failure replanning scenario).

**Response:** `valid`, `declared_infeasible`, `agrees_with_ground_truth`,
`violation_codes[]`, `summary`, `report_json` (the full typed report), `error`.

Payloads are JSON in the fleet-plan-bench schema, not mirrored `.msg` types, so the ROS
interface cannot drift from the pydantic models. Validation takes milliseconds, so the
service runs on the node's default executor.

## Run with Docker

```bash
docker build -f docker/ros2.Dockerfile --target runtime -t fleet-plan-validator:jazzy .
docker run --rm -it --network host fleet-plan-validator:jazzy \
  ros2 launch fleet_plan_validator_ros validator.launch.py default_scenario:=e01_orchard_mowing
```

From another shell on the same ROS domain:

```bash
fpb show e01_orchard_mowing --reference > plan.json      # a known-good plan
python3 -c 'import json,yaml; print(yaml.safe_dump({"plan": open("plan.json").read()}, width=10**9))' > req.yaml
ros2 service call /fleet_plan_validator/validate_plan \
  fleet_plan_validator_interfaces/srv/ValidatePlan "$(cat req.yaml)"
# -> valid=True, summary='Scenario e01_orchard_mowing: PASS (makespan 25.5)', ...
```

Run the package tests in the image (the build fails if any test fails):

```bash
docker build -f docker/ros2.Dockerfile --target test .
```

## Call it from your own node

```python
from fleet_plan_validator_interfaces.srv import ValidatePlan

client = node.create_client(ValidatePlan, "/fleet_plan_validator/validate_plan")
req = ValidatePlan.Request(scenario="m03_mine_bench", plan=plan_json)
future = client.call_async(req)
# ...when done:
res = future.result()
if not res.valid:
    node.get_logger().warning(f"plan rejected: {list(res.violation_codes)}")
```

Or skip the service and call the core directly inside your node:
`from fleet_plan_bench.validator import validate`.

## Build natively (without Docker)

The core needs **pydantic v2**, but rosdep resolves `python3-pydantic` to the apt v1
package, so it isn't listed in `package.xml`. Install the core with pip into a venv that
can also see the ROS Python packages, and build with that venv's Python:

```bash
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages ~/fpb-venv && touch ~/fpb-venv/COLCON_IGNORE
source ~/fpb-venv/bin/activate
pip install /path/to/repo                 # the core (pin a version for reproducibility)
cd /path/to/repo && python -m colcon build --base-paths ros2
source install/setup.bash
ros2 launch fleet_plan_validator_ros validator.launch.py
```

Use `python -m colcon` (not plain `colcon`) so the node's entry point runs with the
venv's Python. Don't install pytest 8 or newer into that venv: ROS's `launch_testing`
pytest plugins need the apt pytest (7.x on Jazzy).

## Dev container

`.devcontainer/devcontainer.json` uses the `dev` target of `docker/ros2.Dockerfile`, which
has ROS 2 Jazzy, the venv and the toolchain. On creation it runs
`pip install -e '.[dev,ortools,llm]'` and `scripts/ros2_build.sh`. Inside:

```bash
pytest && ruff check . && mypy src           # core
scripts/ros2_build.sh --test                 # ROS 2 packages: colcon build + test
source install/setup.bash && ros2 launch fleet_plan_validator_ros validator.launch.py
```
