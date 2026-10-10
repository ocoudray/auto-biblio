"""From items, similarities and signals to feature vectors (pure)."""

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from auto_biblio.domain.features import (
    FeatureVector,
    SourceFamily,
    ThemeId,
    context_level,
    families_seen,
    grouped_percentiles,
    item_family,
)
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Signal, SignalKind
from auto_biblio.domain.scoring import popularity, relevance, velocity
from auto_biblio.domain.selection import is_revenant
from auto_biblio.repo_config.profile import Profile
from auto_biblio.repo_config.triage import TriageConfig

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class ProfileView:
    """What the scoring needs from the profile."""

    weights: Mapping[ThemeId, float]
    keywords: Mapping[ThemeId, tuple[str, ...]]
    watched_repos: frozenset[str]
    watched_authors: frozenset[str]
    exclusions: tuple[str, ...]

    @classmethod
    def of(cls, profile: Profile) -> "ProfileView":
        """Extract the view of a profile.

        Args:
            profile: The interest profile.

        Returns:
            Theme weights and keywords, watch lists and every exclusion rule.
        """
        return cls(
            weights={ThemeId(t.id): t.weight for t in profile.themes},
            keywords={ThemeId(t.id): t.keywords for t in profile.themes},
            watched_repos=frozenset(profile.watched_repos()),
            watched_authors=frozenset(a.lower() for t in profile.themes for a in t.watch.authors),
            exclusions=(*profile.global_exclude, *(r for t in profile.themes for r in t.exclude)),
        )

    def is_watched(self, item: Item) -> bool:
        """Tell whether an item comes from a watched repository or author.

        Args:
            item: The item.

        Returns:
            True for a watched repository (or one of its releases) or author.
        """
        repo = item.id.removeprefix("gh:").split("@", 1)[0].lower()
        if item.id.startswith("gh:") and repo in self.watched_repos:
            return True
        return any(author.lower() in self.watched_authors for author in item.authors)


def keyword_similarities(item: Item, view: ProfileView) -> dict[ThemeId, float]:
    """Fallback similarity when embeddings are unavailable: 1 if a theme keyword appears.

    Args:
        item: The item.
        view: The profile view.

    Returns:
        1.0 or 0.0 per theme.
    """
    text = f"{item.title}\n{item.summary or ''}"
    return {
        theme: float(
            any(re.search(rf"\b{re.escape(k)}\b", text, flags=re.IGNORECASE) for k in keywords)
        )
        for theme, keywords in view.keywords.items()
    }


@dataclass(frozen=True)
class FeatureInputs:
    """Everything `build_features` reads."""

    population: Sequence[Item]
    """Items the percentiles are computed against (the reference window)."""
    pool: Sequence[Item]
    """Items that may become candidates: the week's items and older active ones."""
    similarities: Mapping[ItemId, Mapping[ThemeId, float]]
    histories: Mapping[ItemId, Sequence[Signal]]
    last_shown: Mapping[ItemId, datetime]
    window_start: datetime
    now: datetime


def build_features(
    inputs: FeatureInputs, view: ProfileView, cfg: TriageConfig
) -> dict[ItemId, FeatureVector]:
    """Compute the features of the pool items that may become candidates.

    Items of the window are kept; older items only when they are revenants.

    Args:
        inputs: Items, similarities, signal histories and showing dates.
        view: The profile view.
        cfg: The triage configuration.

    Returns:
        Features per candidate-able item.
    """
    every = {item.id: item for item in (*inputs.population, *inputs.pool)}
    families: dict[ItemId, SourceFamily] = {i: item_family(item) for i, item in every.items()}
    percentiles = _theme_percentiles(every, families, inputs.similarities, cfg)
    pops = _popularities(every, inputs, cfg)
    features: dict[ItemId, FeatureVector] = {}
    for item in inputs.pool:
        old = item.first_seen < inputs.window_start
        revenant = old and is_revenant(
            item,
            item_popularity=pops[item.id],
            window_start=inputs.window_start,
            now=inputs.now,
            cfg=cfg.revenant,
            last_shown=inputs.last_shown.get(item.id),
        )
        if old and not revenant:
            continue
        features[item.id] = _vector(
            item,
            family=families[item.id],
            theme_pct=percentiles[item.id],
            item_popularity=pops[item.id],
            revenant=revenant,
            inputs=inputs,
            view=view,
        )
    return features


def _theme_percentiles(
    every: Mapping[ItemId, Item],
    families: Mapping[ItemId, SourceFamily],
    similarities: Mapping[ItemId, Mapping[ThemeId, float]],
    cfg: TriageConfig,
) -> dict[ItemId, dict[ThemeId, float]]:
    themes = sorted({t for sims in similarities.values() for t in sims})
    result: dict[ItemId, dict[ThemeId, float]] = {item_id: {} for item_id in every}
    for theme in themes:
        values = {i: similarities[i].get(theme, 0.0) for i in every if i in similarities}
        ranks = grouped_percentiles(values, families, cfg.min_family_population)
        for item_id, rank in ranks.items():
            result[item_id][theme] = rank
    return result


def _popularities(
    every: Mapping[ItemId, Item], inputs: FeatureInputs, cfg: TriageConfig
) -> dict[ItemId, float]:
    velocities: dict[ItemId, dict[SignalKind, float | None]] = {}
    populations: defaultdict[SignalKind, list[float]] = defaultdict(list)
    for item_id, item in every.items():
        by_kind: defaultdict[SignalKind, list[Signal]] = defaultdict(list)
        for signal in inputs.histories.get(item_id, ()):
            by_kind[signal.kind].append(signal)
        velocities[item_id] = {
            kind: velocity(history, inputs.window_start, inputs.now, item.first_seen)
            for kind, history in by_kind.items()
        }
        for kind, value in velocities[item_id].items():
            if value is not None:
                populations[kind].append(value)
    return {
        item_id: popularity(v, populations, cfg.neutral_popularity)
        for item_id, v in velocities.items()
    }


def _vector(  # noqa: PLR0913 - assembles one vector from already computed parts
    item: Item,
    *,
    family: SourceFamily,
    theme_pct: dict[ThemeId, float],
    item_popularity: float,
    revenant: bool,
    inputs: FeatureInputs,
    view: ProfileView,
) -> FeatureVector:
    born = item.published_at or item.first_seen
    return FeatureVector(
        item_id=item.id,
        family=family,
        context_level=context_level(item, None),
        theme_similarity=dict(inputs.similarities.get(item.id, {})),
        theme_percentile=theme_pct,
        relevance=relevance(theme_pct, view.weights),
        popularity=item_popularity,
        source_count=len(families_seen(item)),
        watched=view.is_watched(item),
        revenant=revenant,
        age_days=(inputs.now - born).total_seconds() / SECONDS_PER_DAY,
    )
