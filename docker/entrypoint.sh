#!/bin/bash
# Source ROS 2 and, if present, the built workspace, then run the command.
set -e
source "/opt/ros/${ROS_DISTRO}/setup.bash"
for ws in /ws/install/setup.bash "${PWD}/install/setup.bash"; do
  if [ -f "$ws" ]; then
    source "$ws"
    break
  fi
done
exec "$@"
