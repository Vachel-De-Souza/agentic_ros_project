"""LLM planner adapter for the Anthropic API (optional extra: ``fleet-plan-bench[llm]``).

The model receives the scenario (without ground truth) and must return a plan or an
infeasibility declaration as JSON. On repair attempts it also receives its previous plan
and the validator's typed violations. The LLM only proposes; the deterministic validator
judges. Credentials come from the environment (``ANTHROPIC_API_KEY`` or an ``ant auth``
profile) and are never stored by this package.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from fleet_plan_bench.planners.base import PlannerUnavailableError, RepairFeedback, Usage
from fleet_plan_bench.planners.llm_common import (
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    LLMOutputError,
    extract_json,
    feedback_prompt,
    scenario_prompt,
    to_planner_output,
)
from fleet_plan_bench.schemas import Infeasible, Plan, Scenario

__all__ = ["AnthropicPlanner", "LLMOutputError", "LLMPlannerConfig", "extract_json"]

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class LLMPlannerConfig:
    model: str = field(default_factory=lambda: os.environ.get("FPB_LLM_MODEL", DEFAULT_MODEL))
    max_tokens: int = 16000
    effort: str | None = "high"
    """``output_config.effort``; None leaves the model default."""
    structured_output: bool = True
    """Constrain the response to OUTPUT_SCHEMA via ``output_config.format``."""
    server_fallbacks: bool = True
    """Opt into server-side refusal fallbacks (beta). The serving model is recorded."""
    reserve_fraction: float = 0.10


def _is_transient(exc: Exception) -> bool:
    """Connection problems, timeouts, rate limits and 5xx: not the model's fault."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - a fake client is in use
        return False
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.RateLimitError)):
        return True
    return isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500


class AnthropicPlanner:
    """Plans with a Claude model. Pass ``client`` to inject a custom or fake client."""

    repairable = True

    def __init__(self, config: LLMPlannerConfig | None = None, client: Any = None) -> None:
        self.config = config or LLMPlannerConfig()
        self.name = f"llm:{self.config.model}"
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise ImportError(
                    "AnthropicPlanner needs the 'llm' extra: pip install 'fleet-plan-bench[llm]'"
                ) from exc
            client = anthropic.Anthropic()  # reads credentials from the environment
        self.client = client
        self.last_usage: Usage | None = None
        self.last_raw: str | None = None

    def _request(self, scenario: Scenario, feedback: RepairFeedback | None) -> dict[str, Any]:
        cfg = self.config
        content = "Scenario:\n" + scenario_prompt(scenario)
        if feedback is not None:
            content += "\n\n" + feedback_prompt(feedback)
        req: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "system": SYSTEM_PROMPT.format(reserve=cfg.reserve_fraction),
            "messages": [{"role": "user", "content": content}],
        }
        output_config: dict[str, Any] = {}
        if cfg.effort:
            output_config["effort"] = cfg.effort
        if cfg.structured_output:
            output_config["format"] = {"type": "json_schema", "schema": OUTPUT_SCHEMA}
        if output_config:
            req["output_config"] = output_config
        return req

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Plan | Infeasible:
        req = self._request(scenario, feedback)
        t0 = time.perf_counter()
        try:
            if self.config.server_fallbacks:
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **req
                )
            else:
                resp = self.client.messages.create(**req)
        except Exception as exc:
            if _is_transient(exc):
                raise PlannerUnavailableError(f"Anthropic API unavailable: {exc}") from exc
            raise
        latency = time.perf_counter() - t0
        usage = getattr(resp, "usage", None)
        self.last_usage = Usage(
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_s=latency,
            extra={
                "served_model": getattr(resp, "model", None),
                "stop_reason": getattr(resp, "stop_reason", None),
            },
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            raise LLMOutputError("model refused the request", raw="")
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        self.last_raw = text
        try:
            return to_planner_output(extract_json(text), self.name)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise LLMOutputError(f"could not parse model output: {exc}", raw=text) from exc
