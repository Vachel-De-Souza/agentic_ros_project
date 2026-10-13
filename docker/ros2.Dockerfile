# syntax=docker/dockerfile:1
#
# ROS 2 image for fleet-plan-bench and its ROS 2 wrapper.
#
# Targets:
#   dev      - toolchain only; the VS Code dev container mounts the repo (see .devcontainer/)
#   runtime  - core + ROS 2 packages built into /ws; runs the validator node
#   test     - runtime + colcon test (the build fails if any test fails)
#
# The core needs pydantic v2, but apt/rosdep only ship pydantic v1. So Python packages live
# in a venv at /opt/venv created with --system-site-packages: it sees rclpy and the other
# apt-installed ROS packages, and pip-installed packages shadow anything older from apt.
# Building with the venv's python makes the generated node entry points use the venv too.

ARG ROS_DISTRO=jazzy
ARG BASE_IMAGE=ros:${ROS_DISTRO}-ros-base

FROM ${BASE_IMAGE} AS dev
ARG ROS_DISTRO
ENV ROS_DISTRO=${ROS_DISTRO} \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv python3-pip git \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/venv \
    && touch /opt/venv/COLCON_IGNORE \
    && echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /etc/bash.bashrc
# Keep ROS's apt pytest (its launch_testing plugins need it) but run it with the venv's
# python, so a bare `pytest` sees the venv packages.
RUN printf '#!/bin/sh\nexec /opt/venv/bin/python -m pytest "$@"\n' > /opt/venv/bin/pytest \
    && chmod +x /opt/venv/bin/pytest
COPY docker/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]

FROM dev AS runtime
# Core, pinned to this checkout so ROS results match the pip benchmark exactly.
WORKDIR /opt/fleet-plan-bench
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[ortools]"
# ROS 2 workspace
WORKDIR /ws
COPY ros2 ./src
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
    && python -m colcon build --event-handlers console_direct-
CMD ["ros2", "launch", "fleet_plan_validator_ros", "validator.launch.py"]

FROM runtime AS test
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && . /ws/install/setup.sh \
    && python -m colcon test --event-handlers console_direct+ \
    && python -m colcon test-result --verbose
