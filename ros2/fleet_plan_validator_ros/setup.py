from glob import glob

from setuptools import find_packages, setup

package_name = "fleet_plan_validator_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    # The validator core (fleet-plan-bench, pydantic v2) is installed with pip, not
    # rosdep: apt only ships pydantic v1. See ros2/README.md.
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vachel De Souza",
    maintainer_email="97903267+Vachel-De-Souza@users.noreply.github.com",
    description="ROS 2 node exposing the deterministic fleet-plan-bench validator.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": ["validator_node = fleet_plan_validator_ros.node:main"],
    },
)
