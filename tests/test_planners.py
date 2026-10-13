from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from fleet_plan_bench.io import find_scenario, load_builtin_scenarios
from fleet_plan_bench.planners import GreedyPlanner, Planner, RepairFeedback, get_planner
from fleet_plan_bench.planners.llm_anthropic import (
    AnthropicPlanner,
    LLMOutputError,
    LLMPlannerConfig,
    extract_json,
)
from fleet_plan_bench.schemas import (
    Infeasible,
    Plan,
    Scenario,
    Violation,
    ViolationCode,
    apply_perturbation,
)
from fleet_plan_bench.validator import validate

SCENARIOS = load_builtin_scenarios()
ALL = SCENARIOS + [apply_perturbation(s) for s in SCENARIOS if s.perturbation]


@pytest.mark.parametrize("scenario", ALL, ids=lambda s: s.id)
def test_greedy_matches_ground_truth(scenario: Scenario) -> None:
    out = GreedyPlanner().plan(scenario)
    if scenario.is_feasible:
        assert isinstance(out, Plan)
        assert validate(scenario, out).valid
    else:
        assert isinstance(out, Infeasible)
        assert out.reason


def test_greedy_is_deterministic() -> None:
    s = find_scenario("h01_harvest_chain")
    assert GreedyPlanner().plan(s) == GreedyPlanner().plan(s)


def test_builtin_planners_satisfy_protocol() -> None:
    assert isinstance(GreedyPlanner(), Planner)
    assert isinstance(get_planner("greedy"), GreedyPlanner)
    with pytest.raises(ValueError, match="unknown planner"):
        get_planner("magic")


@pytest.mark.parametrize("scenario", ALL, ids=lambda s: s.id)
def test_ortools_matches_ground_truth_and_beats_greedy(scenario: Scenario) -> None:
    pytest.importorskip("ortools")
    from fleet_plan_bench.planners.ortools_planner import ORToolsPlanner

    out = ORToolsPlanner().plan(scenario)
    if scenario.is_feasible:
        assert isinstance(out, Plan)
        report = validate(scenario, out)
        assert report.valid, report.summary()
        greedy = GreedyPlanner().plan(scenario)
        assert isinstance(greedy, Plan)
        assert out.makespan() <= greedy.makespan() + 1e-6
    else:
        assert isinstance(out, Infeasible)


# --- LLM adapter, with a fake client (no network, no API key) -----------------------


class FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        text = self.replies.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=1234, output_tokens=56),
            model=kwargs["model"],
            stop_reason="end_turn",
        )


class FakeClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = FakeMessages(replies)
        self.beta = SimpleNamespace(messages=self.messages)


def _reply_from(plan: Plan) -> str:
    data = plan.model_dump(mode="json", exclude={"planner", "notes"})
    data["reason"] = ""
    return json.dumps(data)


def test_llm_planner_parses_plan_and_records_usage() -> None:
    s = find_scenario("e01_orchard_mowing")
    ref = s.ground_truth.reference_plan
    assert ref is not None
    client = FakeClient([_reply_from(ref)])
    planner = AnthropicPlanner(LLMPlannerConfig(model="test-model"), client=client)
    out = planner.plan(s)
    assert isinstance(out, Plan)
    assert validate(s, out).valid
    assert out.planner == "llm:test-model"
    assert planner.last_usage is not None
    assert planner.last_usage.input_tokens == 1234
    assert planner.last_usage.latency_s is not None
    req = client.messages.requests[0]
    assert req["model"] == "test-model"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["fallbacks"] == "default"
    prompt = req["messages"][0]["content"]
    assert "ground_truth" not in prompt and "reference_plan" not in prompt


def test_llm_planner_repair_prompt_and_infeasible() -> None:
    s = find_scenario("e04_spray_without_sprayer")
    reply = json.dumps({"kind": "infeasible", "reason": "nobody can spray", "assignments": []})
    client = FakeClient([reply])
    planner = AnthropicPlanner(
        LLMPlannerConfig(model="m", server_fallbacks=False, structured_output=False),
        client=client,
    )
    fb = RepairFeedback(
        attempt=1,
        previous=Plan(assignments=[]),
        violations=[Violation(code=ViolationCode.TASK_UNASSIGNED, message="task mow_a ...")],
    )
    out = planner.plan(s, fb)
    assert isinstance(out, Infeasible)
    req = client.messages.requests[0]
    assert "fallbacks" not in req and "format" not in req.get("output_config", {})
    assert "TASK_UNASSIGNED" in req["messages"][0]["content"]


def test_llm_planner_bad_output_raises() -> None:
    s = find_scenario("e01_orchard_mowing")
    planner = AnthropicPlanner(LLMPlannerConfig(model="m"), client=FakeClient(["no plan, sorry"]))
    with pytest.raises(LLMOutputError):
        planner.plan(s)


def test_extract_json_tolerates_fences_and_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": 2} hope it helps') == {"a": 2}


def test_llm_model_name_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FPB_LLM_MODEL", "some-model")
    assert LLMPlannerConfig().model == "some-model"
    monkeypatch.delenv("FPB_LLM_MODEL")
    assert LLMPlannerConfig().model == "claude-opus-5-5"


# --- Ollama adapter, with a fake transport (no network) ------------------------------


class FakeOllama:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def __call__(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float):  # type: ignore[no-untyped-def]
        self.calls.append((url, payload, headers))
        out = self.responses.pop(0)
        if isinstance(out, Exception):
            raise out
        return {"model": payload["model"], "response": out, "prompt_eval_count": 900,
                "eval_count": 120, "done_reason": "stop"}  # fmt: skip


def test_ollama_planner_plan_usage_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleet_plan_bench.planners.llm_ollama import OllamaPlanner, OllamaPlannerConfig

    monkeypatch.setenv("FPB_OLLAMA_API_KEY", "test-token")
    s = find_scenario("e01_orchard_mowing")
    ref = s.ground_truth.reference_plan
    assert ref is not None
    fake = FakeOllama([_reply_from(ref)])
    planner = OllamaPlanner(OllamaPlannerConfig(model="m:1b", url="http://srv/"), transport=fake)
    out = planner.plan(s)
    assert isinstance(out, Plan) and validate(s, out).valid
    assert out.planner == "ollama:m:1b"
    url, payload, headers = fake.calls[0]
    assert url == "http://srv/api/generate"
    assert payload["stream"] is False and payload["options"]["temperature"] == 0
    assert payload["format"]["type"] == "object"
    assert payload["think"] is False
    assert "ground_truth" not in payload["prompt"]
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["User-Agent"].startswith("fleet-plan-bench/")
    assert planner.last_usage is not None and planner.last_usage.output_tokens == 120


def test_ollama_planner_errors_and_url_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleet_plan_bench.planners.llm_ollama import OllamaPlanner, OllamaPlannerConfig

    monkeypatch.delenv("FPB_OLLAMA_URL", raising=False)
    s = find_scenario("e01_orchard_mowing")
    cfg = OllamaPlannerConfig(model="m", url="https://srv/api/generate")
    assert cfg.endpoint == "https://srv/api/generate"
    with pytest.raises(ValueError, match="FPB_OLLAMA_URL"):
        _ = OllamaPlannerConfig(model="m").endpoint
    for bad in ["not json at all", OSError("connection refused")]:
        planner = OllamaPlanner(cfg, transport=FakeOllama([bad]))
        with pytest.raises(LLMOutputError):
            planner.plan(s)


def test_get_planner_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FPB_OLLAMA_URL", "http://srv")
    p = get_planner("ollama:qwen:7b")
    assert p.name == "ollama:qwen:7b"


def test_ollama_planner_reads_thinking_when_response_empty() -> None:
    from fleet_plan_bench.planners.llm_ollama import OllamaPlanner, OllamaPlannerConfig

    s = find_scenario("e04_spray_without_sprayer")
    reply = json.dumps({"kind": "infeasible", "reason": "no sprayer", "assignments": []})

    def transport(url, payload, headers, timeout):  # type: ignore[no-untyped-def]
        return {"model": "m", "response": "", "thinking": reply}

    out = OllamaPlanner(OllamaPlannerConfig(model="m", url="http://x"), transport).plan(s)
    assert isinstance(out, Infeasible)
