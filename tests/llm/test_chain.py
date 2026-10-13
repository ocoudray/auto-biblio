import pytest
from scripted import CONFIG, ScriptedRunner, ignore_fallback, make_task

from auto_biblio.domain.errors import (
    BudgetExhaustedError,
    ChainExhaustedError,
    LLMOutputInvalidError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from auto_biblio.llm.chain import ModelChain


def chain(runner: ScriptedRunner) -> tuple[ModelChain, list[tuple[str, str, str]]]:
    fallbacks: list[tuple[str, str, str]] = []

    def record(role: str, model_id: str, reason: str) -> None:
        fallbacks.append((role, model_id, reason))

    return ModelChain(runner, CONFIG, record), fallbacks


def test_first_model_answers() -> None:
    llm, fallbacks = chain(ScriptedRunner({"t:free": [1]}))
    result = llm.run(make_task())
    assert result.output.value == 1
    assert result.usage.fallback_from is None
    assert fallbacks == []


def test_chain_retries_once_with_error() -> None:
    runner = ScriptedRunner({"t:free": [LLMOutputInvalidError("t:free", "missing i02"), 2]})
    llm, _ = chain(runner)
    assert llm.run(make_task()).output.value == 2
    assert runner.calls[0] == ("t:free", "u")
    assert "missing i02" in runner.calls[1][1]


def test_chain_falls_back_and_reports() -> None:
    runner = ScriptedRunner({"t:free": [ProviderQuotaError("t:free", "429")], "t:paid": [3]})
    llm, fallbacks = chain(runner)
    result = llm.run(make_task())
    assert result.output.value == 3
    assert result.usage.fallback_from == "t:free"
    assert fallbacks == [("triage", "t:free", "ProviderQuotaError")]


def test_invalid_twice_falls_back() -> None:
    bad = LLMOutputInvalidError("t:free", "bad")
    runner = ScriptedRunner({"t:free": [bad, bad], "t:paid": [4]})
    llm, _ = chain(runner)
    assert llm.run(make_task()).output.value == 4


def test_chain_exhausted() -> None:
    runner = ScriptedRunner(
        {
            "t:free": [ProviderUnavailableError("t:free", "down")],
            "t:paid": [ProviderQuotaError("t:paid", "429")],
        }
    )
    llm, fallbacks = chain(runner)
    with pytest.raises(ChainExhaustedError) as excinfo:
        llm.run(make_task())
    assert excinfo.value.attempts == ("t:free: down", "t:paid: 429")
    assert len(fallbacks) == 2


def test_budget_error_does_not_fall_back() -> None:
    runner = ScriptedRunner({"t:free": [BudgetExhaustedError("tokens", 10, 1)], "t:paid": [5]})
    llm, fallbacks = chain(runner)
    with pytest.raises(BudgetExhaustedError):
        llm.run(make_task())
    assert fallbacks == []


def test_spent_daily_quota_skips_the_model_for_the_rest_of_the_run() -> None:
    daily = ProviderQuotaError("t:free", "daily quota", transient=False)
    runner = ScriptedRunner({"t:free": [daily], "t:paid": [1, 2]})
    llm, fallbacks = chain(runner)
    llm.run(make_task("a"))
    second = llm.run(make_task("b"))
    assert second.output.value == 2
    assert second.usage.fallback_from == "t:free"
    assert [model for model, _ in runner.calls] == ["t:free", "t:paid", "t:paid"]
    assert fallbacks == [("triage", "t:free", "ProviderQuotaError")]


def test_transient_failure_does_not_skip_the_model_later() -> None:
    runner = ScriptedRunner(
        {"t:free": [ProviderUnavailableError("t:free", "503"), 2], "t:paid": [1]}
    )
    llm, _ = chain(runner)
    llm.run(make_task("a"))
    assert llm.run(make_task("b")).output.value == 2


def test_prompt_too_large_for_the_tokens_per_minute_cap_skips_the_model() -> None:
    small = CONFIG.models["free"].model_copy(update={"tpm": 5_000, "max_output_tokens": 1_000})
    config = CONFIG.model_copy(update={"models": {**CONFIG.models, "free": small}})
    runner = ScriptedRunner({"t:free": [1], "t:paid": [2]})
    llm = ModelChain(runner, config, ignore_fallback)
    assert llm.run(make_task("x" * 100)).output.value == 1
    result = llm.run(make_task("x" * 20_000))
    assert result.output.value == 2
    assert result.usage.fallback_from == "t:free"


def test_chain_exhausted_names_skipped_models() -> None:
    small = CONFIG.models["free"].model_copy(update={"tpm": 10})
    config = CONFIG.model_copy(update={"models": {**CONFIG.models, "free": small}})
    runner = ScriptedRunner({"t:paid": [ProviderQuotaError("t:paid", "429")]})
    with pytest.raises(ChainExhaustedError) as excinfo:
        ModelChain(runner, config, ignore_fallback).run(make_task())
    assert "t:free: skipped" in excinfo.value.attempts[0]
