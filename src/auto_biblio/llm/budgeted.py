"""Budget enforcement around each model call."""

from pydantic import BaseModel

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.llm import LLMResult, LLMTask, ModelRunner
from auto_biblio.repo_config.llm import ModelSpec


class BudgetedRunner:
    """`ModelRunner` that reserves the estimated cost before a call and settles it after.

    Sits below the chain, so that every model tried, retries included, is accounted for.
    """

    def __init__(self, inner: ModelRunner, ledger: BudgetLedger) -> None:
        """Build the runner.

        Args:
            inner: The runner doing the call.
            ledger: The weekly budget.
        """
        self._inner = inner
        self._ledger = ledger

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        """Run a task within budget.

        Args:
            task: The task.
            spec: The model.

        Returns:
            The inner result.

        Raises:
            BudgetExhaustedError: If the call could exceed the budget (nothing is called).
        """
        chars = len(task.system_prompt) + len(task.user_prompt)
        reservation = self._ledger.reserve(*self._ledger.estimate(spec, chars))
        try:
            result = self._inner.run(task, spec)
        except BaseException:
            # The provider bills nothing for a failed call that we can observe; only
            # the reservation has to go.
            self._ledger.release(reservation)
            raise
        self._ledger.settle(reservation, result.usage)
        return result
