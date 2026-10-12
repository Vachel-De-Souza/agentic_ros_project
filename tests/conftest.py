from __future__ import annotations

import copy
from typing import Any

import pytest

from fleet_plan_bench.schemas import Plan, Scenario

# A tiny synthetic site used by the unit tests.
#
#   D --10-- A --10-- B --10-- C        D: depot + charger
#   |        |                 |        X: no-go zone
#   +--------|-------40--------+        D-B (30) is a no-go edge
#            +--5-- X --5------+
TOY: dict[str, Any] = {
    "id": "toy",
    "tier": "easy",
    "domain": "agriculture",
    "fleet": [
        {
            "id": "m1",
            "type": "tractor",
            "capabilities": ["till"],
            "speed": 10,
            "payload_capacity": 100,
            "battery_capacity": 100,
            "energy_per_distance": 1,
            "charge_rate": 10,
            "start_zone": "D",
        },
        {
            "id": "m2",
            "type": "truck",
            "capabilities": ["haul"],
            "speed": 5,
            "payload_capacity": 50,
            "battery_capacity": 30,
            "energy_per_distance": 1,
            "charge_rate": 5,
            "start_zone": "D",
        },
    ],
    "site": {
        "zones": [
            {"id": "D", "kind": "depot"},
            {"id": "A"},
            {"id": "B"},
            {"id": "C"},
            {"id": "X", "no_go": True},
        ],
        "edges": [
            {"a": "D", "b": "A", "distance": 10},
            {"a": "A", "b": "B", "distance": 10},
            {"a": "B", "b": "C", "distance": 10},
            {"a": "D", "b": "C", "distance": 40},
            {"a": "A", "b": "X", "distance": 5},
            {"a": "X", "b": "C", "distance": 5},
            {"a": "D", "b": "B", "distance": 30, "no_go": True},
        ],
        "charging_stations": ["D"],
    },
    "mission": {
        "tasks": [
            {"id": "t1", "required_capability": "till", "zone": "A", "duration": 5},
            {
                "id": "t2",
                "required_capability": "haul",
                "zone": "B",
                "duration": 4,
                "payload_demand": 40,
                "precedence": ["t1"],
            },
            {
                "id": "t3",
                "required_capability": "till",
                "zone": "C",
                "duration": 3,
                "time_window": {"earliest_start": 0, "latest_end": 100},
            },
        ]
    },
    "ground_truth": {"feasible": True},
}

TOY_PLAN: dict[str, Any] = {
    "assignments": [
        {"machine": "m1", "task": "t1", "route": ["D", "A"], "start": 1, "end": 6},
        {"machine": "m1", "task": "t3", "route": ["A", "B", "C"], "start": 8, "end": 11},
        {"machine": "m2", "task": "t2", "route": ["D", "A", "B"], "start": 6, "end": 10},
    ]
}


@pytest.fixture
def toy_dict() -> dict[str, Any]:
    return copy.deepcopy(TOY)


@pytest.fixture
def toy(toy_dict: dict[str, Any]) -> Scenario:
    return Scenario.model_validate(toy_dict)


@pytest.fixture
def plan_dict() -> dict[str, Any]:
    return copy.deepcopy(TOY_PLAN)


@pytest.fixture
def good_plan(plan_dict: dict[str, Any]) -> Plan:
    return Plan.model_validate(plan_dict)
