import pytest
from pydantic import ValidationError

from auto_biblio.repo_config.triage import TriageConfig


def test_triage_defaults_match_spec() -> None:
    cfg = TriageConfig()
    assert cfg.window_days == 7
    assert cfg.reference_days == 28
    assert cfg.min_family_population == 30
    assert cfg.embed_summary_words == 30
    assert cfg.context_max_words == 150
    assert cfg.neutral_popularity == 0.5
    assert cfg.weights.relevance == 0.60
    assert cfg.weights.popularity == 0.25
    assert cfg.weights.multi_source == 0.10
    assert cfg.weights.watched == 0.15
    assert cfg.relevance_gate == 0.75
    assert cfg.candidates == 50
    assert cfg.family_floor == 5
    assert cfg.discovery.slots == 2
    assert cfg.discovery.min_popularity == 0.95
    assert cfg.llm_weight == 0.6
    assert cfg.llm_gate == 1
    assert cfg.selected == 18
    assert cfg.per_theme_max == 4
    assert cfg.revenant.min_age_days == 30
    assert cfg.revenant.min_popularity == 0.90
    assert cfg.revenant.cooldown_weeks == 8
    assert cfg.refresh.horizon_days == 180
    assert cfg.refresh.max_items_per_day == 1000
    assert cfg.learning.min_reliable_labels == 50
    assert cfg.learning.min_per_polarity == 10
    assert cfg.learning.min_auc == 0.65
    assert cfg.learning.weak_negative_weight == 0.2
    assert cfg.learning.weak_negative_grace_days == 14
    assert cfg.learning.cv_folds == 5
    assert cfg.alert_after_days == 8


@pytest.mark.parametrize(
    "raw",
    [
        {"relevance_gate": 1.5},
        {"selected": 0},
        {"llm_gate": 6},
        {"learning": {"cv_folds": 1}},
        {"neutral_popularity": -0.1},
    ],
)
def test_triage_bounds(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TriageConfig.model_validate(raw)


@pytest.mark.parametrize(
    "raw",
    [
        {"selected": 3, "per_theme_max": 4},
        {"candidates": 10, "family_floor": 5},
        {"learning": {"min_reliable_labels": 10, "min_per_polarity": 10}},
    ],
)
def test_triage_cross_validators(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TriageConfig.model_validate(raw)


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        TriageConfig.model_validate({"relevance_gat": 0.5})
