import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from auto_biblio.domain.errors import (
    LLMOutputInvalidError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from auto_biblio.llm import LLMTask
from auto_biblio.llm.pydantic_ai import PydanticAIRunner
from auto_biblio.repo_config.llm import ModelSpec

SPEC = ModelSpec(id="test:m", input_usd_per_mtok=1, output_usd_per_mtok=2, batch_size=5)


class Answer(BaseModel):
    value: int


def task(validate_max: int | None = None) -> LLMTask[Answer]:
    def check(answer: Answer, model_id: str) -> Answer:
        if validate_max is not None and answer.value > validate_max:
            raise LLMOutputInvalidError(model_id, "too big")
        return answer

    return LLMTask(
        role="triage",
        prompt_version="v1",
        system_prompt="sys",
        user_prompt="user",
        output_type=Answer,
        validate=check,
    )


def runner(model: Model) -> PydanticAIRunner:
    return PydanticAIRunner(lambda _spec: model)


def raising(exc: Exception) -> FunctionModel:
    def respond(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise exc

    return FunctionModel(respond)


def test_runner_returns_validated_output() -> None:
    result = runner(TestModel(custom_output_args={"value": 3})).run(task(), SPEC)
    assert result.output == Answer(value=3)
    assert result.usage.model_id == "test:m"
    assert result.usage.input_tokens > 0
    assert result.usage.cost_usd == pytest.approx(
        SPEC.cost_usd(result.usage.input_tokens, result.usage.output_tokens)
    )
    assert not result.usage.cached


def test_runner_maps_429_to_quota() -> None:
    with pytest.raises(ProviderQuotaError):
        runner(raising(ModelHTTPError(429, "m"))).run(task(), SPEC)


@pytest.mark.parametrize(
    "exc",
    [ModelHTTPError(503, "m"), ModelAPIError("m", "connection reset"), httpx.ConnectError("down")],
)
def test_runner_maps_unavailable(exc: Exception) -> None:
    with pytest.raises(ProviderUnavailableError):
        runner(raising(exc)).run(task(), SPEC)


def test_runner_maps_unparseable_output() -> None:
    with pytest.raises(LLMOutputInvalidError):
        runner(TestModel(custom_output_args={"value": "not a number"})).run(task(), SPEC)


def test_runner_applies_task_validation() -> None:
    with pytest.raises(LLMOutputInvalidError, match="too big"):
        runner(TestModel(custom_output_args={"value": 9})).run(task(validate_max=5), SPEC)
