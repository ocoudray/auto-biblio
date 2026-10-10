import pytest

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import BudgetExhaustedError
from auto_biblio.domain.triage import LLMUsage
from auto_biblio.repo_config.llm import Budget, ModelSpec

PAID = ModelSpec(
    id="m:paid", input_usd_per_mtok=1, output_usd_per_mtok=5, batch_size=10, max_output_tokens=1000
)
FREE = ModelSpec(
    id="m:free", input_usd_per_mtok=0, output_usd_per_mtok=0, batch_size=10, max_output_tokens=1000
)


def usage(usd: float, tokens_in: int, tokens_out: int) -> LLMUsage:
    return LLMUsage(
        role="triage",
        model_id="m",
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        cost_usd=usd,
        cached=False,
    )


def test_estimate() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=100_000))
    usd, tokens = ledger.estimate(PAID, prompt_chars=4000)
    assert tokens == 1200 + 1000
    assert usd == pytest.approx((1200 * 1 + 1000 * 5) / 1_000_000)


def test_reserve_within_limits() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=10_000))
    ledger.reserve(0.5, 4000)
    assert ledger.remaining_usd == pytest.approx(0.5)
    assert ledger.remaining_tokens == 6000


def test_reserve_over_usd_raises() -> None:
    ledger = BudgetLedger(Budget(usd=0.01, tokens=10_000))
    with pytest.raises(BudgetExhaustedError) as excinfo:
        ledger.reserve(0.02, 10)
    assert excinfo.value.limit == "usd"


def test_reserve_over_tokens_raises() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=100))
    with pytest.raises(BudgetExhaustedError) as excinfo:
        ledger.reserve(0.0, 101)
    assert excinfo.value.limit == "tokens"


def test_free_model_counts_tokens_only() -> None:
    ledger = BudgetLedger(Budget(usd=0, tokens=10_000))
    usd, tokens = ledger.estimate(FREE, prompt_chars=400)
    ledger.reserve(usd, tokens)
    assert usd == 0
    assert ledger.remaining_tokens == 10_000 - tokens


def test_settle_replaces_estimate() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=10_000))
    reservation = ledger.reserve(0.5, 5000)
    ledger.settle(reservation, usage(0.1, 800, 200))
    assert ledger.remaining_usd == pytest.approx(0.9)
    assert ledger.remaining_tokens == 9000


def test_release_frees_reservation() -> None:
    ledger = BudgetLedger(Budget(usd=1, tokens=10_000))
    ledger.release(ledger.reserve(0.5, 5000))
    assert ledger.remaining_usd == 1
    assert ledger.remaining_tokens == 10_000


def test_ledger_starts_from_previous_usage() -> None:
    ledger = BudgetLedger(Budget(usd=0.5, tokens=1000), spent_usd=0.5, spent_tokens=900)
    with pytest.raises(BudgetExhaustedError):
        ledger.reserve(0.01, 10)
    with pytest.raises(BudgetExhaustedError):
        ledger.reserve(0.0, 101)
