from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument("default_scenario", default_value=""),
        DeclareLaunchArgument("reserve_fraction", default_value="0.1"),
        DeclareLaunchArgument("check_single_lane", default_value="false"),
    ]
    node = Node(
        package="fleet_plan_validator_ros",
        executable="validator_node",
        name="fleet_plan_validator",
        output="screen",
        parameters=[
            {
                "default_scenario": LaunchConfiguration("default_scenario"),
                "reserve_fraction": LaunchConfiguration("reserve_fraction"),
                "check_single_lane": LaunchConfiguration("check_single_lane"),
            }
        ],
    )
    return LaunchDescription([*args, node])
