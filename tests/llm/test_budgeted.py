import pytest
from scripted import CONFIG, ScriptedRunner, make_task

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import BudgetExhaustedError, ProviderUnavailableError
from auto_biblio.llm.budgeted import BudgetedRunner
from auto_biblio.repo_config.llm import Budget

PAID = CONFIG.models["paid"]


def test_budgeted_settles_real_usage() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=100_000))
    BudgetedRunner(ScriptedRunner({"t:paid": [1]}), ledger).run(make_task(), PAID)
    assert ledger.remaining_tokens == 100_000 - 110
    assert ledger.remaining_usd == pytest.approx(1 - PAID.cost_usd(100, 10))


def test_budgeted_releases_on_failure() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=100_000))
    runner = ScriptedRunner({"t:paid": [ProviderUnavailableError("t:paid", "down")]})
    with pytest.raises(ProviderUnavailableError):
        BudgetedRunner(runner, ledger).run(make_task(), PAID)
    assert ledger.remaining_tokens == 100_000


def test_budgeted_refuses_before_calling() -> None:
    runner = ScriptedRunner({"t:paid": [1]})
    with pytest.raises(BudgetExhaustedError):
        BudgetedRunner(runner, BudgetLedger(Budget(usd=1, tokens=10))).run(make_task(), PAID)
    assert runner.calls == []
