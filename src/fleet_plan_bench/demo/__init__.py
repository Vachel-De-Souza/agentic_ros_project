"""Live demo: an AI (or any planner) plans, the validator checks and repairs, the plan plays
back, a machine fails mid-mission and the rest is replanned.

Phase 1 runs in the browser with no extra dependencies (``fpb demo``). The optional
``ros2/fleet_plan_sim`` package drives the same runner in Gazebo (phase 2).
"""

from fleet_plan_bench.demo.dashboard import Dashboard
from fleet_plan_bench.demo.runner import DemoConfig, DemoRunner, Mover, NullMover

__all__ = ["Dashboard", "DemoConfig", "DemoRunner", "Mover", "NullMover"]
