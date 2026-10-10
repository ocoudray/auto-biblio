"""`ModelRunner` backed by pydantic-ai, which speaks to every provider we use."""

from collections.abc import Callable

import httpx
from pydantic import BaseModel
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
            if exc.status_code == HTTP_TOO_MANY_REQUESTS:
                raise ProviderQuotaError(spec.id, str(exc)) from exc
            raise ProviderUnavailableError(spec.id, str(exc)) from exc
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
