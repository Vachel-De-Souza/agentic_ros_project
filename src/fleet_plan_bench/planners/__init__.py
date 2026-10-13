from fleet_plan_bench.planners.base import (
    Planner,
    PlannerUnavailableError,
    RepairFeedback,
    Usage,
)
from fleet_plan_bench.planners.greedy import GreedyPlanner

__all__ = [
    "GreedyPlanner",
    "Planner",
    "PlannerUnavailableError",
    "RepairFeedback",
    "Usage",
    "get_planner",
]


def get_planner(name: str) -> Planner:
    """Build a built-in planner by name.

    ``greedy``, ``ortools``, ``llm[:<anthropic-model>]`` or ``ollama:<model-tag>``
    (Ollama server URL from ``FPB_OLLAMA_URL``).
    """
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
    if name.startswith("ollama:"):
        from fleet_plan_bench.planners.llm_ollama import OllamaPlanner, OllamaPlannerConfig

        return OllamaPlanner(OllamaPlannerConfig(model=name.split(":", 1)[1]))
    raise ValueError(
        f"unknown planner {name!r} (expected greedy, ortools, llm[:model] or ollama:<model>)"
    )
