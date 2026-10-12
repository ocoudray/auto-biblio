"""Fallback chain: try each model of a role in turn."""

import logging
from collections.abc import Callable

from pydantic import BaseModel

from auto_biblio.domain.errors import (
    ChainExhaustedError,
    LLMOutputInvalidError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from auto_biblio.llm import LLMResult, LLMTask, ModelRunner
from auto_biblio.repo_config.llm import LLMConfig, ModelSpec

logger = logging.getLogger(__name__)

type FallbackHook = Callable[[str, str, str], None]
"""Called with (role, failed model, reason) each time the chain moves on."""


class ModelChain:
    """`StructuredLLM` that falls back along the chain of models configured for a role.

    An invalid output gets one retry with the validation error before moving on. A
    budget error is not a model failure: it propagates at once.
    """

    def __init__(self, runner: ModelRunner, config: LLMConfig, on_fallback: FallbackHook) -> None:
        """Build the chain.

        Args:
            runner: Runs one call with one model.
            config: The model catalogue and chains.
            on_fallback: Notified of every fallback.
        """
        self._runner = runner
        self._config = config
        self._on_fallback = on_fallback

    def run[T: BaseModel](self, task: LLMTask[T]) -> LLMResult[T]:
        """Run a task with the first model of the chain that succeeds.

        Args:
            task: The task.

        Returns:
            The validated output; `usage.fallback_from` names the first model if it failed.

        Raises:
            ChainExhaustedError: If every model failed.
        """
        attempts: list[str] = []
        chain = self._config.chain(task.role)
        for spec in chain:
            try:
                result = self._run_with_retry(task, spec)
            except (ProviderQuotaError, ProviderUnavailableError, LLMOutputInvalidError) as exc:
                attempts.append(str(exc))  # already prefixed with the model id
                logger.warning("model %s failed for %s: %s", spec.id, task.role, exc)
                self._on_fallback(task.role, spec.id, type(exc).__name__)
                continue
            if attempts:
                usage = result.usage.model_copy(update={"fallback_from": chain[0].id})
                return LLMResult(output=result.output, usage=usage)
            return result
        raise ChainExhaustedError(task.role, tuple(attempts))

    def _run_with_retry[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        try:
            return self._runner.run(task, spec)
        except LLMOutputInvalidError as exc:
            logger.info("retrying %s on %s after invalid output: %s", task.role, spec.id, exc)
            return self._runner.run(task.with_feedback(str(exc)), spec)
