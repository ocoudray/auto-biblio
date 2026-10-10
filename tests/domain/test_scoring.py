import math
from datetime import timedelta

import pytest
from builders import NOW, make_signal

from auto_biblio.domain.features import FeatureVector, ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.scoring import (
    ThemeAnchors,
    fixed_final_score,
    llm_relevance,
    popularity,
    prescore,
    relevance,
    theme_similarities,
    velocity,
)
from auto_biblio.domain.triage import TriageVerdict
from auto_biblio.repo_config.triage import ScoringWeights

T1, T2 = ThemeId("t1"), ThemeId("t2")
WEEK_AGO = NOW - timedelta(days=7)


def features(**overrides: object) -> FeatureVector:
    base: dict[str, object] = {
        "item_id": ItemId("arxiv:1"),
        "family": "paper",
        "context_level": "abstract",
        "theme_similarity": {},
        "theme_percentile": {},
        "relevance": 0.8,
        "popularity": 0.5,
        "source_count": 2,
        "watched": True,
        "revenant": False,
        "age_days": 1.0,
    }
    return FeatureVector.model_validate(base | overrides)


def test_similarity_takes_best_anchor() -> None:
    anchors = [
        ThemeAnchors(theme=T1, weight=1.0, vectors=((1.0, 0.0), (0.0, 1.0))),
        ThemeAnchors(theme=T2, weight=1.0, vectors=((-1.0, 0.0),)),
    ]
    sims = theme_similarities((0.0, 1.0), anchors)
    assert sims == {T1: pytest.approx(1.0), T2: pytest.approx(0.0)}


def test_relevance_applies_theme_weight() -> None:
    assert relevance({T1: 0.9, T2: 0.8}, {T1: 0.5, T2: 1.0}) == pytest.approx(0.8)
    assert relevance({}, {}) == 0.0


def test_velocity_new_item_single_observation() -> None:
    history = [make_signal(value=800, observed_at=NOW)]
    result = velocity(history, WEEK_AGO, NOW, first_seen=NOW - timedelta(days=2))
    assert result == pytest.approx(math.log1p(800) / 2)


def test_velocity_delta_over_window() -> None:
    history = [
        make_signal(value=100, observed_at=NOW - timedelta(days=10)),
        make_signal(value=150, observed_at=NOW - timedelta(days=3)),
        make_signal(value=200, observed_at=NOW),
    ]
    result = velocity(history, WEEK_AGO, NOW, first_seen=NOW - timedelta(days=40))
    assert result == pytest.approx(math.log1p(100) / 7)


def test_velocity_old_item_two_observations_in_window() -> None:
    history = [
        make_signal(value=10, observed_at=NOW - timedelta(days=4)),
        make_signal(value=30, observed_at=NOW),
    ]
    result = velocity(history, WEEK_AGO, NOW, first_seen=NOW - timedelta(days=40))
    assert result == pytest.approx(math.log1p(20) / 4)


def test_velocity_negative_delta_clamped() -> None:
    history = [
        make_signal(value=50, observed_at=NOW - timedelta(days=8)),
        make_signal(value=40, observed_at=NOW),
    ]
    assert velocity(history, WEEK_AGO, NOW, first_seen=NOW - timedelta(days=60)) == 0.0


def test_velocity_none_without_observation() -> None:
    history = [make_signal(observed_at=NOW - timedelta(days=30))]
    assert velocity(history, WEEK_AGO, NOW, first_seen=NOW - timedelta(days=30)) is None


def test_no_signal_is_neutral() -> None:
    assert popularity({}, {}, neutral=0.5) == 0.5
    assert popularity({"gh_stars": None}, {"gh_stars": [1.0]}, neutral=0.5) == 0.5


def test_popularity_takes_max_kind() -> None:
    result = popularity(
        {"gh_stars": 1.0, "hn_points": 5.0},
        {"gh_stars": [1.0, 2.0, 3.0, 4.0], "hn_points": [1.0, 2.0, 3.0, 4.0]},
        neutral=0.5,
    )
    assert result == 1.0


def test_prescore_formula() -> None:
    weights = ScoringWeights()
    # 0.60 x 0.8 + 0.25 x 0.5 + 0.10 x 0.5 + 0.15 x 1
    assert prescore(features(), weights) == pytest.approx(0.48 + 0.125 + 0.05 + 0.15)


def test_llm_relevance_scales_to_unit() -> None:
    verdict = TriageVerdict(
        ref="i01",
        relevance={T1: 5, T2: 4},
        item_type="tool",
        novelty="high",
        confidence="high",
        reason="ok",
    )
    assert llm_relevance(verdict, {T1: 0.5, T2: 1.0}) == pytest.approx(0.8)
    empty = verdict.model_copy(update={"relevance": {}})
    assert llm_relevance(empty, {T1: 1.0}) == 0.0


def test_fixed_final_score() -> None:
    assert fixed_final_score(0.5, 1.0, 0.6) == pytest.approx(0.8)
