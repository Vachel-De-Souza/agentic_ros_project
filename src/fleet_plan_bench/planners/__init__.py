from fleet_plan_bench.planners.base import Planner, RepairFeedback, Usage
from fleet_plan_bench.planners.greedy import GreedyPlanner

__all__ = ["GreedyPlanner", "Planner", "RepairFeedback", "Usage", "get_planner"]


def get_planner(name: str) -> Planner:
    """Build a built-in planner by name: ``greedy``, ``ortools`` or ``llm[:<model>]``."""
    if name == "greedy":
        return GreedyPlanner()
    if name == "ortools":
        from fleet_plan_bench.planners.ortools_planner import ORToolsPlanner

        return ORToolsPlanner()
    if name == "llm" or name.startswith("llm:"):
        from fleet_plan_bench.planners.llm_anthropic import AnthropicPlanner, LLMPlannerConfig

        cfg = LLMPlannerConfig()
        if name.startswith("llm:"):
            cfg.model = name.split(":", 1)[1]
        return AnthropicPlanner(cfg)
    raise ValueError(f"unknown planner {name!r} (expected greedy, ortools or llm[:model])")
