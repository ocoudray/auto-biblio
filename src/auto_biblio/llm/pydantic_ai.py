"""`ModelRunner` backed by pydantic-ai, which speaks to every provider we use."""

import re
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from auto_biblio.domain.errors import (
    LLMOutputInvalidError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from auto_biblio.domain.triage import LLMUsage
from auto_biblio.llm import LLMResult, LLMTask
from auto_biblio.repo_config.llm import ModelSpec

HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
MESSAGE_MAX = 160
"""Provider messages are cut to this length: they end up in journals and the digest."""

_RETRY_DELAY = re.compile(r"^(\d+)(?:\.\d+)?s$")
_DAILY_QUOTA = "PerDay"


class _Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    quota_id: str = Field(default="", alias="quotaId")


class _Detail(BaseModel):
    model_config = ConfigDict(frozen=True)

    retry_delay: str | None = Field(default=None, alias="retryDelay")
    violations: tuple[_Violation, ...] = ()


class _Error(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str
    details: tuple[_Detail, ...] = ()


class _ErrorBody(BaseModel):
    """Error payload of the Google API; other providers fall back to the raw message."""

    model_config = ConfigDict(frozen=True)

    error: _Error


def _http_error(
    exc: ModelHTTPError, model_id: str
) -> ProviderQuotaError | ProviderUnavailableError:
    try:
        error = _ErrorBody.model_validate(exc.body).error
    except ValidationError:
        error = _Error(message=str(exc.body or exc.message))
    first_line = error.message.strip().split("\n", 1)[0]
    message = f"HTTP {exc.status_code}: {first_line[:MESSAGE_MAX]}"
    delays = [
        m.group(1)
        for d in error.details
        if d.retry_delay and (m := _RETRY_DELAY.match(d.retry_delay))
    ]
    daily = any(_DAILY_QUOTA in v.quota_id for d in error.details for v in d.violations)
    quota = exc.status_code == HTTP_TOO_MANY_REQUESTS
    # A client error (unknown model, bad request) or a spent daily quota will not clear today.
    transient = (quota and not daily) or exc.status_code >= HTTP_SERVER_ERROR
    error_type = ProviderQuotaError if quota else ProviderUnavailableError
    return error_type(model_id, message, retry_after=next(iter(delays), None), transient=transient)


class PydanticAIRunner:
    """Runs one structured call with pydantic-ai and maps its errors onto ours."""

    def __init__(self, model_factory: Callable[[ModelSpec], Model]) -> None:
        """Build the runner.

        Args:
            model_factory: Builds the pydantic-ai model of a spec (with its credentials).
        """
        self._model_factory = model_factory

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        """Run a task with a model.

        Args:
            task: The task.
            spec: The model.

        Returns:
            The validated output and its usage.

        Raises:
            ProviderQuotaError: On HTTP 429.
            ProviderUnavailableError: On any other provider or network failure.
            LLMOutputInvalidError: If the output does not parse or fails the task validation.
        """
        # retries=0: validation retries are driven by ModelChain, which records them.
        agent = Agent(
            self._model_factory(spec),
            output_type=task.output_type,
            system_prompt=task.system_prompt,
            retries=0,
        )
        try:
            result = agent.run_sync(
                task.user_prompt, model_settings=ModelSettings(max_tokens=spec.max_output_tokens)
            )
        except ModelHTTPError as exc:
            raise _http_error(exc, spec.id) from exc
        except (ModelAPIError, httpx.HTTPError) as exc:
            raise ProviderUnavailableError(spec.id, str(exc)) from exc
        except UnexpectedModelBehavior as exc:
            raise LLMOutputInvalidError(spec.id, str(exc)) from exc
        usage = result.usage
        output = task.validate(result.output, spec.id)
        return LLMResult(
            output=output,
            usage=LLMUsage(
                role=task.role,
                model_id=spec.id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=spec.cost_usd(usage.input_tokens, usage.output_tokens),
                cached=False,
            ),
        )
