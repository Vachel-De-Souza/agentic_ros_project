from glob import glob

from setuptools import find_packages, setup

package_name = "fleet_plan_sim"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    # The core (fleet-plan-bench, pydantic v2) is pip-installed; see ros2/README.md.
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vachel De Souza",
    maintainer_email="97903267+Vachel-De-Souza@users.noreply.github.com",
    description="Gazebo live demo for fleet-plan-bench: AI plans, validator, playback.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "demo_node = fleet_plan_sim.node:main",
            "fpb-sim-world = fleet_plan_sim.make_world:main",
        ],
    },
)
