import pytest
from scripted import CONFIG, ScriptedRunner, make_task

from auto_biblio.domain.errors import (
    LLMOutputInvalidError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from auto_biblio.llm.paced import PacedRunner
from auto_biblio.repo_config.llm import ModelSpec

FREE = CONFIG.models["free"]


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def paced(runner: ScriptedRunner, clock: FakeTime) -> PacedRunner:
    return PacedRunner(runner, monotonic=clock.monotonic, sleep=clock.sleep)


def spec(**update: float) -> ModelSpec:
    return FREE.model_copy(update=update)


def test_calls_to_a_model_are_spaced() -> None:
    clock = FakeTime()
    runner = paced(ScriptedRunner({"t:free": [1, 2]}), clock)
    runner.run(make_task(), spec(min_interval_s=12.0))
    clock.now += 2.0
    runner.run(make_task(), spec(min_interval_s=12.0))
    assert clock.sleeps == [10.0]


def test_models_are_paced_independently() -> None:
    clock = FakeTime()
    runner = paced(ScriptedRunner({"t:free": [1], "t:paid": [2]}), clock)
    runner.run(make_task(), spec(min_interval_s=12.0))
    runner.run(make_task(), CONFIG.models["paid"])
    assert clock.sleeps == []


def test_transient_error_is_retried_after_the_delay_asked() -> None:
    clock = FakeTime()
    quota = ProviderQuotaError("t:free", "429", retry_after="18")
    runner = paced(ScriptedRunner({"t:free": [quota, 3]}), clock)
    assert runner.run(make_task(), FREE).output.value == 3
    assert clock.sleeps == [18.0]


def test_retries_back_off_then_give_up() -> None:
    clock = FakeTime()
    down = ProviderUnavailableError("t:free", "503")
    runner = paced(ScriptedRunner({"t:free": [down, down, down]}), clock)
    with pytest.raises(ProviderUnavailableError):
        runner.run(make_task(), spec(max_retries=2))
    assert clock.sleeps == [10.0, 20.0]


def test_non_transient_error_is_not_retried() -> None:
    clock = FakeTime()
    daily = ProviderQuotaError("t:free", "daily quota", transient=False)
    runner = paced(ScriptedRunner({"t:free": [daily]}), clock)
    with pytest.raises(ProviderQuotaError):
        runner.run(make_task(), FREE)
    assert clock.sleeps == []


def test_invalid_output_is_left_to_the_chain() -> None:
    clock = FakeTime()
    runner = paced(ScriptedRunner({"t:free": [LLMOutputInvalidError("t:free", "bad")]}), clock)
    with pytest.raises(LLMOutputInvalidError):
        runner.run(make_task(), FREE)
    assert clock.sleeps == []
