"""Pacing and retries around each model call, for free tiers that cap requests per minute."""

import logging
import time
from collections.abc import Callable

from pydantic import BaseModel

from auto_biblio.domain.errors import ProviderQuotaError, ProviderUnavailableError
from auto_biblio.llm import LLMResult, LLMTask, ModelRunner
from auto_biblio.repo_config.llm import ModelSpec
from auto_biblio.sources._http import Throttle

logger = logging.getLogger(__name__)


class PacedRunner:
    """`ModelRunner` that spaces the calls to each model and retries transient refusals.

    A rate limit or an overloaded provider usually clears within seconds: waiting is cheaper
    than handing the task to a weaker model of the chain. A refusal that will not clear
    within the run (daily quota) or that persists after `max_retries` propagates, and the
    chain moves on.
    """

    def __init__(
        self,
        inner: ModelRunner,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Build the runner.

        Args:
            inner: The runner doing the call.
            monotonic: Clock (injected for tests).
            sleep: Sleep function (injected for tests).
        """
        self._inner = inner
        self._monotonic = monotonic
        self._sleep = sleep
        self._throttles: dict[str, Throttle] = {}

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        """Run a task with a model, once its interval has elapsed.

        Args:
            task: The task.
            spec: The model, with its pacing and retry settings.

        Returns:
            The inner result.

        Raises:
            ProviderQuotaError: If the quota refusal is not transient or persists.
            ProviderUnavailableError: If the provider stays unavailable.
        """
        throttle = self._throttle(spec)
        attempt = 0
        while True:
            throttle.wait()
            try:
                return self._inner.run(task, spec)
            except (ProviderQuotaError, ProviderUnavailableError) as exc:
                delay = throttle.retry_delay(attempt, exc.retry_after) if exc.transient else None
                if delay is None:
                    raise
                logger.info("%s refused (%s): retrying in %.0f s", spec.id, exc, delay)
                throttle.pause(delay)
                attempt += 1

    def _throttle(self, spec: ModelSpec) -> Throttle:
        if spec.id not in self._throttles:
            self._throttles[spec.id] = Throttle(
                spec.min_interval_s, self._monotonic, self._sleep, max_retries=spec.max_retries
            )
        return self._throttles[spec.id]
