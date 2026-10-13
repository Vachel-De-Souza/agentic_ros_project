"""LLM planner adapter for an Ollama server (``/api/generate``), standard library only.

Same prompt, output schema and repair feedback as the Anthropic adapter, so results are
comparable across providers. The server URL comes from ``FPB_OLLAMA_URL`` (or the config),
never from this package; an optional bearer token comes from ``FPB_OLLAMA_API_KEY``.
Sampling is pinned (temperature 0, fixed seed) to make runs as repeatable as the server
allows; the validator itself is deterministic either way.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from fleet_plan_bench import __version__
from fleet_plan_bench.planners.base import RepairFeedback, Usage
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

URL_ENV = "FPB_OLLAMA_URL"
KEY_ENV = "FPB_OLLAMA_API_KEY"


@dataclass
class OllamaPlannerConfig:
    model: str
    url: str = field(default_factory=lambda: os.environ.get(URL_ENV, ""))
    """Server base URL (``https://host``) or the full ``.../api/generate`` endpoint."""
    structured_output: bool = True
    """Send OUTPUT_SCHEMA as Ollama's ``format`` to constrain the response."""
    think: bool | None = False
    """Ollama's ``think`` flag; None leaves the server default. Off by default because with
    ``format`` set, Ollama constrains a thinking model's reasoning to the schema too and
    returns the answer in ``thinking`` with an empty ``response``."""
    temperature: float = 0.0
    seed: int = 0
    num_ctx: int | None = 16384
    """Context window; scenarios plus repair feedback exceed Ollama's small default."""
    timeout_s: float = 600.0
    reserve_fraction: float = 0.10

    @property
    def endpoint(self) -> str:
        base = self.url.rstrip("/")
        if not base:
            raise ValueError(f"set {URL_ENV} to the Ollama server URL")
        return base if base.endswith("/api/generate") else base + "/api/generate"


Transport = Any  # callable(url, payload: dict, headers: dict, timeout: float) -> dict


def _http_post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class OllamaPlanner:
    """Plans with a model served by Ollama. Pass ``transport`` to inject a fake for tests."""

    repairable = True

    def __init__(self, config: OllamaPlannerConfig, transport: Transport | None = None) -> None:
        self.config = config
        self.name = f"ollama:{config.model}"
        self.transport = transport or _http_post
        self.last_usage: Usage | None = None
        self.last_raw: str | None = None

    def _payload(self, scenario: Scenario, feedback: RepairFeedback | None) -> dict[str, Any]:
        cfg = self.config
        prompt = "Scenario:\n" + scenario_prompt(scenario)
        if feedback is not None:
            prompt += "\n\n" + feedback_prompt(feedback)
        options: dict[str, Any] = {"temperature": cfg.temperature, "seed": cfg.seed}
        if cfg.num_ctx:
            options["num_ctx"] = cfg.num_ctx
        payload: dict[str, Any] = {
            "model": cfg.model,
            "system": SYSTEM_PROMPT.format(reserve=cfg.reserve_fraction),
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        payload["format"] = OUTPUT_SCHEMA if cfg.structured_output else "json"
        if cfg.think is not None:
            payload["think"] = cfg.think
        return payload

    def plan(self, scenario: Scenario, feedback: RepairFeedback | None = None) -> Plan | Infeasible:
        cfg = self.config
        # An explicit User-Agent: some proxies/CDNs reject Python's default "Python-urllib".
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"fleet-plan-bench/{__version__}",
        }
        if key := os.environ.get(KEY_ENV):
            headers["Authorization"] = f"Bearer {key}"
        payload = self._payload(scenario, feedback)
        t0 = time.perf_counter()
        try:
            data = self.transport(cfg.endpoint, payload, headers, cfg.timeout_s)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            self.last_usage = Usage(latency_s=time.perf_counter() - t0)
            raise LLMOutputError(f"Ollama request failed: {exc}", raw="") from exc
        latency = time.perf_counter() - t0
        self.last_usage = Usage(
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            latency_s=latency,
            extra={"served_model": data.get("model"), "done_reason": data.get("done_reason")},
        )
        text = str(data.get("response") or "")
        if not text.strip():  # thinking models can return the JSON in "thinking" instead
            text = str(data.get("thinking") or "")
        self.last_raw = text
        try:
            return to_planner_output(extract_json(text), self.name)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise LLMOutputError(f"could not parse model output: {exc}", raw=text) from exc
