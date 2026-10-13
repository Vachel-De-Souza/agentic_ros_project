#!/bin/bash
# Build (and optionally test) the ROS 2 packages in ros2/ from the repo root.
# Run inside the dev container, or anywhere ROS 2 is installed and the core is
# pip-installed into the active Python environment.
#   scripts/ros2_build.sh          # build
#   scripts/ros2_build.sh --test   # build + colcon test
set -eo pipefail  # no -u: ROS setup scripts reference unset variables
cd "$(dirname "$0")/.."
source "/opt/ros/${ROS_DISTRO:?set ROS_DISTRO or source ROS 2 first}/setup.bash"
python -m colcon build --base-paths ros2 --event-handlers console_direct-
if [ "${1:-}" = "--test" ]; then
  source install/setup.bash
  python -m colcon test --base-paths ros2 --event-handlers console_direct+
  python -m colcon test-result --verbose
fi
echo "Built. Run: source install/setup.bash && ros2 launch fleet_plan_validator_ros validator.launch.py"
