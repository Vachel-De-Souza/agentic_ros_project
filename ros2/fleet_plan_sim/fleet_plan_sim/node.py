"""ROS 2 node running the live demo against Gazebo through the ros_gz bridge.

Vehicles are moved with ``/world/<world>/set_pose`` (ros_gz_interfaces/SetEntityPose,
bridged by ros_gz_bridge). The dashboard runs on ``dashboard_port``.

Parameters: scenario, planner, fallback, failure ("scenario" = the scenario's own
perturbation, "none", or "machine@time"), mission_seconds, max_repairs, dashboard_port,
novnc_port, autostart. All are dynamically typed, so launch values like "45" or "45.0" work.
"""

from __future__ import annotations

import math
import os
import threading

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from ros_gz_interfaces.msg import Entity
from ros_gz_interfaces.srv import SetEntityPose

from fleet_plan_bench.demo import Dashboard, DemoConfig, DemoRunner
from fleet_plan_bench.io import find_scenario
from fleet_plan_bench.planners import get_planner
from fleet_plan_sim.world import WORLD_NAME


class GzMover:
    """Fire-and-forget pose updates; drops a frame for a vehicle whose last call is pending."""

    def __init__(self, node: Node, world: str = WORLD_NAME) -> None:
        self.client = node.create_client(SetEntityPose, f"/world/{world}/set_pose")
        self.pending: dict[str, object] = {}

    def wait(self, timeout_s: float = 60.0) -> bool:
        return bool(self.client.wait_for_service(timeout_sec=timeout_s))

    def set_pose(
        self, name: str, x: float, y: float, z: float, yaw: float, roll: float = 0.0
    ) -> None:
        prev = self.pending.get(name)
        if prev is not None and not prev.done():  # type: ignore[attr-defined]
            return
        req = SetEntityPose.Request()
        req.entity = Entity(name=name, type=Entity.MODEL)
        # ROS message fields require real floats (an int such as 0 aborts the process)
        pos = req.pose.position
        pos.x, pos.y, pos.z = float(x), float(y), float(z)
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        q = req.pose.orientation
        q.w, q.x, q.y, q.z = cr * cy, sr * cy, sr * sy, cr * sy  # q_yaw * q_roll
        self.pending[name] = self.client.call_async(req)


def _failure(value: str) -> tuple[str, float] | None:
    if value in ("", "scenario", "none"):
        return None
    machine, _, t = value.partition("@")
    return machine, float(t)


class DemoNode(Node):
    def __init__(self) -> None:
        super().__init__("fleet_plan_demo")
        scenario = find_scenario(self._param("scenario", "h05_excavator_breakdown"))
        default_planner = os.environ.get("FPB_DEMO_PLANNER", "ollama:gemma4:12b")
        planner_name = self._param("planner", default_planner)
        fallback_name = self._param("fallback", "ortools")
        failure = self._param("failure", "scenario")
        config = DemoConfig(
            max_repairs=int(self._param("max_repairs", "3")),
            mission_seconds=float(self._param("mission_seconds", "60.0")),
            failure=_failure(failure),
            fallback=get_planner(fallback_name) if fallback_name not in ("", "none") else None,
        )
        if failure == "none":
            scenario = scenario.model_copy(update={"perturbation": None})
        planner = get_planner(planner_name)
        self.mover = GzMover(self)
        self.runner = DemoRunner(scenario, planner, self.mover, config)
        self.thread: threading.Thread | None = None
        self.dashboard = Dashboard(
            self.runner.snapshot,
            self.start_demo,
            port=int(self._param("dashboard_port", "8080")),
            novnc_port=int(self._param("novnc_port", "6080")),
            view="gazebo",
        )
        self.dashboard.start()
        self.get_logger().info(
            f"dashboard on :{self.dashboard.port}; scenario {scenario.id}; planner {planner.name}"
        )
        if self._param("autostart", "false").lower() in ("true", "1", "yes"):
            self.start_demo()

    def _param(self, name: str, default: str) -> str:
        """Declare a dynamically typed parameter and return it as a string.

        Launch files pass "45", "45.0" or "true" with inferred types; reading every value
        as a string and converting here avoids rclpy's strict type checks.
        """
        value = self.declare_parameter(
            name, default, ParameterDescriptor(dynamic_typing=True)
        ).value
        return str(value)

    def start_demo(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        if not self.mover.wait():
            self.get_logger().error("set_pose service not available; is ros_gz_bridge running?")
            return
        self.runner.run()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = DemoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.dashboard.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
