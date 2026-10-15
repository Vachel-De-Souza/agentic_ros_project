#!/bin/bash
# Start a virtual display, VNC + noVNC (browser view of Gazebo on :6080), then Gazebo,
# the ros_gz bridge and the demo node (dashboard on :8080).
set -eo pipefail  # no -u: ROS setup scripts reference unset variables
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source /ws/install/setup.bash

SCENARIO="${FPB_DEMO_SCENARIO:-h05_excavator_breakdown}"
WORLD_DIR=/tmp/fpb_world
python -m fleet_plan_sim.make_world "$SCENARIO" --out-dir "$WORLD_DIR"

export DISPLAY=:1
# Software OpenGL by default so it runs anywhere; set LIBGL_ALWAYS_SOFTWARE=0 with a GPU.
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
Xvfb :1 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 &
sleep 1
x11vnc -display :1 -nopw -forever -shared -quiet -bg -o /tmp/x11vnc.log
websockify --web /usr/share/novnc 6080 localhost:5900 >/tmp/novnc.log 2>&1 &

echo "Dashboard: http://localhost:8080   (Gazebo view alone: http://localhost:6080/vnc.html)"
exec ros2 launch fleet_plan_sim demo.launch.py \
  world_dir:="$WORLD_DIR" \
  scenario:="$SCENARIO" \
  planner:="${FPB_DEMO_PLANNER:-ollama:gemma4:12b}" \
  fallback:="${FPB_DEMO_FALLBACK:-ortools}" \
  failure:="${FPB_DEMO_FAILURE:-scenario}" \
  mission_seconds:="${FPB_DEMO_SECONDS:-60.0}" \
  autostart:="${FPB_DEMO_AUTOSTART:-false}"
