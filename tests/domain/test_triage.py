from datetime import UTC, datetime

import pytest

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.features import FeatureVector, ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.triage import (
    LLMUsage,
    ScoredItem,
    ScoringReport,
    TriageBatch,
    TriageRun,
    TriageVerdict,
    validate_batch,
)

T = ThemeId("agentic")


def verdict(ref: str, **overrides: object) -> TriageVerdict:
    base: dict[str, object] = {
        "ref": ref,
        "relevance": {T: 4},
        "item_type": "tool",
        "novelty": "high",
        "confidence": "medium",
        "reason": "Short reason.",
    }
    return TriageVerdict.model_validate(base | overrides)


def check(*verdicts: TriageVerdict, refs: tuple[str, ...] = ("i01", "i02")) -> TriageBatch:
    return validate_batch(TriageBatch(verdicts=verdicts), frozenset(refs), frozenset({T}), "m")


def test_validate_batch_ok() -> None:
    batch = check(verdict("i01"), verdict("i02"))
    assert len(batch.verdicts) == 2


def test_validate_batch_missing_ref() -> None:
    with pytest.raises(LLMOutputInvalidError, match=r"missing \['i02'\]"):
        check(verdict("i01"))


def test_validate_batch_unknown_theme() -> None:
    with pytest.raises(LLMOutputInvalidError, match="unknown theme"):
        check(verdict("i01", relevance={"rag": 3}), verdict("i02"))


def test_validate_batch_score_out_of_range() -> None:
    with pytest.raises(LLMOutputInvalidError, match="between 0 and 5"):
        check(verdict("i01", relevance={T: 7}), verdict("i02"))


def test_validate_batch_reason_too_long() -> None:
    with pytest.raises(LLMOutputInvalidError, match="longer than 30 words"):
        check(verdict("i01", reason="word " * 31), verdict("i02"))


def scored(item_id: str, slot: str | None, final: float | None) -> ScoredItem:
    features = FeatureVector(
        item_id=ItemId(item_id),
        family="paper",
        context_level="abstract",
        theme_similarity={},
        theme_percentile={},
        relevance=0.5,
        popularity=0.5,
        source_count=1,
        watched=False,
        revenant=False,
        age_days=1,
    )
    return ScoredItem.model_validate(
        {
            "item_id": item_id,
            "features": features,
            "prescore": 0.5,
            "slot": slot,
            "final_score": final,
        }
    )


def test_run_helpers() -> None:
    run = TriageRun(
        week="2026-W41",
        run_id="r",
        generated_at=datetime(2026, 10, 11, tzinfo=UTC),
        scoring=ScoringReport(version="fixed-v1"),
        items=(scored("a:1", "theme", 0.2), scored("a:2", None, None), scored("a:3", "theme", 0.9)),
        usage=(
            LLMUsage(
                role="triage",
                model_id="m",
                input_tokens=100,
                output_tokens=20,
                cost_usd=0.01,
                cached=False,
            ),
        ),
    )
    assert [s.item_id for s in run.selected()] == ["a:3", "a:1"]
    assert run.shown_ids() == {"a:1", "a:3"}
    assert run.usage_totals() == (0.01, 120)
