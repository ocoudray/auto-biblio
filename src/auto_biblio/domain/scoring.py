"""Scores of the triage: profile relevance, popularity, prescore and final score."""

import math
from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy as np
from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.features import FeatureVector, ThemeId, multi_source, percentile_of
from auto_biblio.domain.models import Signal, SignalKind
from auto_biblio.domain.triage import TriageVerdict
from auto_biblio.repo_config.triage import ScoringWeights

MAX_LLM_SCORE = 5
"""Top of the LLM relevance scale (part of the output format)."""

SECONDS_PER_DAY = 86_400


class ThemeAnchors(BaseModel):
    """The embedded anchors of one theme."""

    model_config = ConfigDict(frozen=True)

    theme: ThemeId
    weight: float
    vectors: tuple[tuple[float, ...], ...]


def theme_similarities(
    vector: Sequence[float], anchors: Sequence[ThemeAnchors]
) -> dict[ThemeId, float]:
    """Compute the similarity of an item with each theme: best cosine over its anchors.

    Vectors are expected L2-normalized, so the cosine is a dot product.

    Args:
        vector: The item's embedding.
        anchors: The anchors of every theme.

    Returns:
        The similarity per theme.
    """
    item = np.asarray(vector, dtype=np.float64)
    return {a.theme: float(np.max(np.asarray(a.vectors, dtype=np.float64) @ item)) for a in anchors}


def relevance(theme_pct: Mapping[ThemeId, float], weights: Mapping[ThemeId, float]) -> float:
    """Combine per-theme percentiles into the profile relevance of an item.

    Args:
        theme_pct: Percentile of the similarity with each theme.
        weights: Weight of each theme in the profile.

    Returns:
        `max_t(weight_t x pct_t)`, 0 without theme.
    """
    return max((weights[t] * pct for t, pct in theme_pct.items()), default=0.0)


def velocity(
    history: Sequence[Signal], window_start: datetime, now: datetime, first_seen: datetime
) -> float | None:
    """Measure how fast a signal grew over the window, on a log scale.

    Args:
        history: The observations of one signal kind for one item.
        window_start: Start of the window.
        now: End of the window.
        first_seen: When the item was first seen.

    Returns:
        `log1p(delta) / days`, or None without observation in the window. An item that
        appeared in the window with a single observation counts its whole value as delta.
    """
    inside = sorted((s for s in history if s.observed_at >= window_start), key=_observed)
    if not inside:
        return None
    if len(inside) == 1 and first_seen >= window_start:
        delta = inside[0].value
        start = first_seen
    else:
        before = [s for s in history if s.observed_at < window_start]
        first = max(before, key=_observed) if before else inside[0]
        delta = max(inside[-1].value - first.value, 0)
        start = max(first.observed_at, window_start)
    days = max((now - start).total_seconds() / SECONDS_PER_DAY, 1.0)
    return math.log1p(delta) / days


def _observed(signal: Signal) -> datetime:
    return signal.observed_at


def popularity(
    velocities: Mapping[SignalKind, float | None],
    populations: Mapping[SignalKind, Sequence[float]],
    neutral: float,
) -> float:
    """Rank an item's popularity against the items carrying the same signals.

    Args:
        velocities: The item's velocity per signal kind (None when not observed).
        populations: Velocities of every item, per signal kind.
        neutral: Popularity of an item without any signal.

    Returns:
        The best percentile over the item's signal kinds, or `neutral`.
    """
    ranks = [
        percentile_of(value, populations.get(kind, ()))
        for kind, value in velocities.items()
        if value is not None
    ]
    return max(ranks, default=neutral)


def prescore(features: FeatureVector, weights: ScoringWeights) -> float:
    """Score an item before the LLM, from its features only.

    Args:
        features: The item's features.
        weights: The prescore weights.

    Returns:
        The weighted sum of relevance, popularity, multi-source and watch bonus.
    """
    return (
        weights.relevance * features.relevance
        + weights.popularity * features.popularity
        + weights.multi_source * multi_source(features.source_count)
        + weights.watched * float(features.watched)
    )


def llm_relevance(verdict: TriageVerdict, weights: Mapping[ThemeId, float]) -> float:
    """Turn the LLM's per-theme scores into one relevance on [0, 1] (theme weights applied).

    Args:
        verdict: The LLM verdict.
        weights: Weight of each theme.

    Returns:
        `max_t(weight_t x relevance_t / 5)`, 0 without theme.
    """
    return max(
        (weights.get(t, 0.0) * score / MAX_LLM_SCORE for t, score in verdict.relevance.items()),
        default=0.0,
    )


def fixed_final_score(prescore_value: float, llm_rel: float, llm_weight: float) -> float:
    """Blend the prescore with the LLM relevance (fixed weights).

    Args:
        prescore_value: The prescore.
        llm_rel: The LLM relevance on [0, 1].
        llm_weight: Share of the LLM in the final score.

    Returns:
        The final score.
    """
    return llm_weight * llm_rel + (1 - llm_weight) * prescore_value
