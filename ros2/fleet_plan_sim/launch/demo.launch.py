"""Gazebo (server + GUI) + ros_gz bridge + demo node.

Generate the world first: ``fpb-sim-world <scenario> --out-dir /tmp/fpb_world``.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

WORLD = "fleet_demo"


def generate_launch_description() -> LaunchDescription:
    world_dir = LaunchConfiguration("world_dir")
    args = [
        DeclareLaunchArgument("world_dir", default_value="/tmp/fpb_world"),
        DeclareLaunchArgument("scenario", default_value="h05_excavator_breakdown"),
        DeclareLaunchArgument("planner", default_value="ollama:gemma4:12b"),
        DeclareLaunchArgument("fallback", default_value="ortools"),
        DeclareLaunchArgument("failure", default_value="scenario"),
        DeclareLaunchArgument("mission_seconds", default_value="60.0"),
        DeclareLaunchArgument("autostart", default_value="false"),
    ]
    gz = ExecuteProcess(
        cmd=[
            "gz",
            "sim",
            "-r",
            [world_dir, "/world.sdf"],
            "--gui-config",
            [world_dir, "/gui.config"],
        ],
        output="screen",
    )
    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[f"/world/{WORLD}/set_pose@ros_gz_interfaces/srv/SetEntityPose"],
        output="screen",
    )
    demo = Node(
        package="fleet_plan_sim",
        executable="demo_node",
        output="screen",
        parameters=[
            {
                "scenario": LaunchConfiguration("scenario"),
                "planner": LaunchConfiguration("planner"),
                "fallback": LaunchConfiguration("fallback"),
                "failure": LaunchConfiguration("failure"),
                "mission_seconds": LaunchConfiguration("mission_seconds"),
                "autostart": LaunchConfiguration("autostart"),
            }
        ],
    )
    return LaunchDescription([*args, gz, bridge, demo])
