"""Integration tests for the rclpy node (need a sourced ROS 2 workspace)."""

from __future__ import annotations

import json
import time

import pytest

rclpy = pytest.importorskip("rclpy")

from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.parameter import Parameter  # noqa: E402
from std_msgs.msg import String  # noqa: E402

from fleet_plan_bench.io import find_scenario  # noqa: E402
from fleet_plan_validator_interfaces.srv import ValidatePlan  # noqa: E402
from fleet_plan_validator_ros.node import ValidatorNode  # noqa: E402

SCENARIO = "e01_orchard_mowing"


@pytest.fixture
def setup():  # type: ignore[no-untyped-def]
    rclpy.init()
    server = ValidatorNode(
        parameter_overrides=[Parameter("default_scenario", Parameter.Type.STRING, SCENARIO)]
    )
    client_node = rclpy.create_node("test_client")
    executor = SingleThreadedExecutor()
    executor.add_node(server)
    executor.add_node(client_node)
    yield executor, client_node
    executor.shutdown()
    server.destroy_node()
    client_node.destroy_node()
    rclpy.shutdown()


def _plan() -> dict:  # type: ignore[type-arg]
    plan = find_scenario(SCENARIO).ground_truth.reference_plan
    assert plan is not None
    return json.loads(plan.model_dump_json())


def _call(executor, node, **fields):  # type: ignore[no-untyped-def]
    client = node.create_client(ValidatePlan, "/fleet_plan_validator/validate_plan")
    assert client.wait_for_service(timeout_sec=10.0)
    future = client.call_async(ValidatePlan.Request(**fields))
    executor.spin_until_future_complete(future, timeout_sec=10.0)
    assert future.done()
    return future.result()


def test_service_valid_and_invalid(setup) -> None:  # type: ignore[no-untyped-def]
    executor, node = setup
    ok = _call(executor, node, scenario=SCENARIO, plan=json.dumps(_plan()))
    assert ok.valid and list(ok.violation_codes) == [] and ok.error == ""

    bad = _plan()
    bad["assignments"][0]["end"] = bad["assignments"][0]["start"]
    res = _call(executor, node, plan=json.dumps(bad))  # empty scenario -> default_scenario
    assert not res.valid
    assert list(res.violation_codes) == ["DURATION_TOO_SHORT"]
    assert json.loads(res.report_json)["violations"][0]["code"] == "DURATION_TOO_SHORT"


def test_service_reports_errors(setup) -> None:  # type: ignore[no-untyped-def]
    executor, node = setup
    res = _call(executor, node, scenario="no_such_scenario", plan="{}")
    assert not res.valid and "scenario" in res.error


def test_topic_interface(setup) -> None:  # type: ignore[no-untyped-def]
    executor, node = setup
    received: list[str] = []
    node.create_subscription(
        String, "/fleet_plan_validator/report", lambda m: received.append(m.data), 10
    )
    pub = node.create_publisher(String, "/fleet_plan_validator/plan", 10)
    deadline = time.monotonic() + 10.0
    while not received and time.monotonic() < deadline:
        pub.publish(String(data=json.dumps(_plan())))
        executor.spin_once(timeout_sec=0.2)
    assert received, "no report received"
    assert json.loads(received[0])["valid"] is True
