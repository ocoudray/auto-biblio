from datetime import date, timedelta

import numpy as np
import pytest
from builders import NOW, make_features, make_run

from auto_biblio.domain.feedback import FeedbackEvent
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.learning import (
    FixedScoring,
    LabeledExample,
    LogisticScoring,
    build_examples,
    cross_validated_auc,
    evaluate_variants,
    fit_scoring,
    grouped_folds,
)
from auto_biblio.domain.triage import ScoredItem, TriageRun
from auto_biblio.repo_config.triage import LearningConfig, ScoringWeights

FIXED = FixedScoring(ScoringWeights(), llm_weight=0.6)
CFG = LearningConfig()
TODAY = date(2026, 10, 10)


def shown(item_id: str, relevance: float = 0.9, llm_rel: float | None = 0.8) -> ScoredItem:
    return ScoredItem(
        item_id=ItemId(item_id),
        features=make_features(item_id, relevance=relevance),
        prescore=0.5,
        llm_rel=llm_rel,
        final_score=0.5,
        slot="theme",
    )


def event(item_id: str, polarity: int, days_ago: float = 1) -> FeedbackEvent:
    return FeedbackEvent.model_validate(
        {
            "item_id": item_id,
            "polarity": polarity,
            "channel": "explicit",
            "at": NOW - timedelta(days=days_ago),
            "digest_week": None,
            "origin": f"issue#{item_id}{days_ago}",
        }
    )


def test_build_examples_labels() -> None:
    old = make_run(
        "2026-W38", (shown("a:up"), shown("a:down"), shown("a:silent")), NOW - timedelta(days=20)
    )
    recent = make_run("2026-W41", (shown("a:fresh"),), NOW - timedelta(days=2))
    not_shown = recent.items[0].model_copy(update={"item_id": "a:hidden", "slot": None})
    recent = recent.model_copy(update={"items": (*recent.items, not_shown)})
    examples = build_examples(
        [old, recent], [event("a:up", 1), event("a:down", -1), event("a:hidden", 1)], NOW, 14
    )
    kinds = {e.item_id: e.kind for e in examples}
    assert kinds == {"a:up": "positive", "a:down": "negative", "a:silent": "weak_negative"}
    assert examples[0].week == "2026-W38"


def test_late_feedback_overrides_weak() -> None:
    run = make_run("2026-W38", (shown("a:1"),), NOW - timedelta(days=30))
    examples = build_examples([run], [event("a:1", -1, 5), event("a:1", 1, 1)], NOW, 14)
    assert [e.kind for e in examples] == ["positive"]


def synthetic(n_weeks: int, per_week: int, *, seed: int, signal: bool) -> list[LabeledExample]:
    rng = np.random.default_rng(seed)
    examples: list[LabeledExample] = []
    for week in range(n_weeks):
        for i in range(per_week):
            relevance = float(rng.random())
            positive = (relevance + rng.normal(0, 0.15) > 0.6) if signal else rng.random() > 0.5
            weak = not signal and i % 5 == 0
            inputs = make_features(f"a:{week}-{i}", relevance=relevance).model_inputs(0.5)
            kind = "weak_negative" if weak else ("positive" if positive else "negative")
            examples.append(
                LabeledExample.model_validate(
                    {
                        "item_id": f"a:{week}-{i}",
                        "week": f"2026-W{week:02}",
                        "inputs": inputs,
                        "kind": kind,
                    }
                )
            )
    return examples


def test_weak_labels_never_in_test_folds() -> None:
    examples = synthetic(6, 20, seed=1, signal=False)
    folds = grouped_folds(examples, 5)
    assert folds
    for _, test in folds:
        assert all(examples[i].reliable for i in test)


def test_folds_grouped_by_week() -> None:
    examples = synthetic(6, 20, seed=2, signal=True)
    for train, test in grouped_folds(examples, 3):
        assert not {examples[i].week for i in train} & {examples[i].week for i in test}


def test_single_week_has_no_fold() -> None:
    assert grouped_folds(synthetic(1, 30, seed=3, signal=True), 5) == []
    assert cross_validated_auc([], CFG, use_weak=False) is None


def test_below_activation_threshold_keeps_fixed() -> None:
    model, report = fit_scoring(synthetic(2, 10, seed=4, signal=True), CFG, FIXED, TODAY)
    assert model is FIXED
    assert report.version == "fixed-v1"
    assert report.reliable_labels == 20
    assert report.auc_without_weak is None


def test_learns_positive_relevance_coefficient() -> None:
    model, report = fit_scoring(synthetic(8, 20, seed=5, signal=True), CFG, FIXED, TODAY)
    assert isinstance(model, LogisticScoring)
    assert report.version == "learned-2026-10-10"
    assert report.auc_without_weak is not None
    assert report.auc_without_weak > 0.8
    assert report.auc_with_weak is None
    assert report.coefficients["relevance"] > 0
    high = make_features(relevance=0.95).model_inputs(0.5)
    low = make_features(relevance=0.05).model_inputs(0.5)
    assert model.score(high) > model.score(low)


def test_low_auc_falls_back_to_fixed() -> None:
    model, report = fit_scoring(synthetic(8, 20, seed=6, signal=False), CFG, FIXED, TODAY)
    assert model is FIXED
    assert report.auc_with_weak is not None
    assert report.auc_without_weak is not None


def test_weak_variant_chosen_when_better() -> None:
    examples = synthetic(8, 20, seed=7, signal=True)
    weak = [
        e.model_copy(update={"kind": "weak_negative", "item_id": f"w:{e.item_id}"})
        for e in examples
        if e.inputs["relevance"] < 0.2
    ]
    model, report = fit_scoring(examples + weak, CFG, FIXED, TODAY)
    assert report.auc_with_weak is not None
    assert model.version.startswith("learned-")


def test_fixed_scoring_formula() -> None:
    verified = make_features(relevance=1.0, popularity=0.0).model_inputs(1.0)
    assert FIXED.score(verified) == pytest.approx(0.6 + 0.4 * 0.6)
    unverified = make_features(relevance=1.0, popularity=0.0).model_inputs(None)
    assert FIXED.score(unverified) == pytest.approx(0.6)


def test_evaluate_variants() -> None:
    result = evaluate_variants(synthetic(8, 20, seed=8, signal=True), CFG, FIXED)
    assert set(result) == {"fixed", "learned", "learned_weak"}
    assert result["fixed"] is not None
    assert result["fixed"] > 0.7
    one_class = [e for e in synthetic(2, 5, seed=9, signal=True) if e.kind == "positive"]
    assert evaluate_variants(one_class, CFG, FIXED)["fixed"] is None


def test_run_type_used() -> None:
    assert isinstance(make_run("2026-W41", ()), TriageRun)
