"""ROS 2 node exposing the deterministic fleet-plan-bench validator.

Interfaces:
- service ``~/validate_plan`` (fleet_plan_validator_interfaces/srv/ValidatePlan)
- topic ``~/plan`` (std_msgs/String, plan JSON) -> ``~/report`` (std_msgs/String, result JSON),
  validated against the ``default_scenario`` parameter.

Parameters: ``default_scenario`` (scenario id, path, or JSON/YAML text), ``reserve_fraction``
(energy reserve, default 0.1), ``check_single_lane`` (experimental conflict check).
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from fleet_plan_bench.validator import ValidatorConfig
from fleet_plan_validator_interfaces.srv import ValidatePlan
from fleet_plan_validator_ros.handler import handle


class ValidatorNode(Node):
    def __init__(self, **kwargs: object) -> None:
        super().__init__("fleet_plan_validator", **kwargs)
        self.declare_parameter("default_scenario", "")
        self.declare_parameter("reserve_fraction", 0.10)
        self.declare_parameter("check_single_lane", False)
        self.create_service(ValidatePlan, "~/validate_plan", self._on_validate)
        self._report_pub = self.create_publisher(String, "~/report", 10)
        self.create_subscription(String, "~/plan", self._on_plan, 10)
        self.get_logger().info("fleet plan validator ready")

    def _config(self) -> ValidatorConfig:
        return ValidatorConfig(
            reserve_fraction=float(self.get_parameter("reserve_fraction").value),
            check_single_lane=bool(self.get_parameter("check_single_lane").value),
        )

    def _default_scenario(self) -> str:
        return str(self.get_parameter("default_scenario").value)

    def _on_validate(
        self, request: ValidatePlan.Request, response: ValidatePlan.Response
    ) -> ValidatePlan.Response:
        result = handle(
            request.scenario,
            request.plan,
            perturbed=request.perturbed,
            default_scenario=self._default_scenario(),
            config=self._config(),
        )
        response.valid = result.valid
        response.declared_infeasible = result.declared_infeasible
        response.agrees_with_ground_truth = result.agrees_with_ground_truth
        response.violation_codes = result.violation_codes
        response.summary = result.summary
        response.report_json = result.report_json
        response.error = result.error
        headline = result.summary.splitlines()[0] if result.summary else "empty result"
        # rclpy fixes the severity per call site, so use two separate calls
        if result.valid:
            self.get_logger().info(headline)
        else:
            self.get_logger().warning(headline)
        return response

    def _on_plan(self, msg: String) -> None:
        result = handle(
            "", msg.data, default_scenario=self._default_scenario(), config=self._config()
        )
        self._report_pub.publish(String(data=json.dumps(result.as_dict())))


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ValidatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
