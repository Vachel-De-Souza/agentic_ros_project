# syntax=docker/dockerfile:1
#
# Gazebo live demo: ROS 2 Jazzy + Gazebo Harmonic, viewed in a browser.
#   docker compose -f docker/compose.demo.yaml up --build   ->   http://localhost:8080
#
# Same Python layout as docker/ros2.Dockerfile: the core (pydantic v2) lives in a venv
# created with --system-site-packages, so it sees rclpy/ros_gz from apt.

ARG BASE_IMAGE=osrf/ros:jazzy-simulation
FROM ${BASE_IMAGE}
ENV ROS_DISTRO=jazzy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3-venv python3-pip xvfb x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/venv && touch /opt/venv/COLCON_IGNORE
WORKDIR /opt/fleet-plan-bench
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[ortools]"
WORKDIR /ws
COPY ros2 ./src
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
    && python -m colcon build --event-handlers console_direct-
COPY docker/sim_entrypoint.sh /sim_entrypoint.sh
EXPOSE 8080 6080
ENTRYPOINT ["/sim_entrypoint.sh"]
