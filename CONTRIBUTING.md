# Contributing to fleet-plan-bench

Thanks for helping. A few ground rules keep the benchmark trustworthy.

## Ground rules

- **Synthetic data only.** Do not contribute proprietary, employer or customer data,
  real site maps, or real vehicle specifications. Scenarios use abstract units.
- **No secrets.** Never commit API keys or tokens. LLM credentials come from environment
  variables only. `.env` files are git-ignored.
- **The validator stays deterministic.** No LLM, randomness or network access in
  `fleet_plan_bench.validator`. A plan's verdict must depend only on the scenario, the plan
  and `ValidatorConfig`.
- **Do not copy code** from the related-work projects listed in the README.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ortools,llm]"
```

## Before you open a PR

```bash
ruff check . && ruff format --check . && pytest && mypy src
```

- New validator checks need a violation code (in `schemas/report.py`, mapped to a
  `Check`), a passing case and a failing case in `tests/test_validator.py`, and a row in
  the README table.
- New scenarios need a reference plan that validates (if feasible), or a witness test (if
  infeasible). See "How to add a scenario" in the README.
- New planners implement the `Planner` protocol. Optional dependencies go in a
  `[project.optional-dependencies]` extra and are imported lazily.
- Keep commits focused and describe *why* in the message.

## Reporting issues

Please include the scenario file, the plan, the `fpb validate --json` output, and what
you expected instead.
