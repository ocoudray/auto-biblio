"""Selection of the triage: exclusions, revenants, preselection, discoveries and quotas."""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from auto_biblio.domain.features import FAMILIES, FAMILY_OF, FeatureVector, SourceFamily, ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item
from auto_biblio.domain.triage import ScoredItem
from auto_biblio.repo_config.triage import RevenantConfig, TriageConfig


def is_excluded(item: Item, rules: Sequence[str]) -> bool:
    """Tell whether an exclusion rule matches an item's title or summary.

    Matching is case-insensitive and on whole words: `crypto` excludes "crypto markets"
    but not "cryptography".

    Args:
        item: The item.
        rules: Exclusion phrases.

    Returns:
        True if any rule matches.
    """
    text = f"{item.title}\n{item.summary or ''}"
    return any(
        re.search(rf"\b{re.escape(rule)}\b", text, flags=re.IGNORECASE) for rule in rules if rule
    )


def is_revenant(  # noqa: PLR0913 - every argument is a distinct input of the rule
    item: Item,
    *,
    item_popularity: float,
    window_start: datetime,
    now: datetime,
    cfg: RevenantConfig,
    last_shown: datetime | None,
) -> bool:
    """Tell whether an old item comes back into fashion.

    Args:
        item: The item.
        item_popularity: Its popularity over the window.
        window_start: Start of the window.
        now: Current time.
        cfg: The revenant rule.
        last_shown: When the item was last shown in a digest, if ever.

    Returns:
        True if the item is old enough, out of its cooldown, and either very popular over
        the window or newly seen by a family that had never seen it.
    """
    born = item.published_at or item.first_seen
    if now - born < timedelta(days=cfg.min_age_days):
        return False
    if last_shown is not None and now - last_shown < timedelta(weeks=cfg.cooldown_weeks):
        return False
    if item_popularity >= cfg.min_popularity:
        return True
    return bool(_new_families(item, window_start))


def _new_families(item: Item, window_start: datetime) -> set[SourceFamily]:
    before: set[SourceFamily] = {
        FAMILY_OF[s.source_type] for s in item.sightings if s.seen_at < window_start
    }
    recent: set[SourceFamily] = {
        FAMILY_OF[s.source_type] for s in item.sightings if s.seen_at >= window_start
    }
    return recent - before if before else set[SourceFamily]()


def _ranked(
    features: Sequence[FeatureVector], prescores: Mapping[ItemId, float]
) -> list[FeatureVector]:
    return sorted(features, key=lambda f: (-prescores[f.item_id], f.item_id))


def preselect(
    features: Sequence[FeatureVector],
    prescores: Mapping[ItemId, float],
    shown: frozenset[ItemId],
    cfg: TriageConfig,
) -> tuple[ItemId, ...]:
    """Pick the candidates sent to the LLM.

    Items must pass the relevance gate and must not have been shown before (unless they
    are revenants). Each family first gets up to `family_floor` slots from its own top,
    then the remaining slots go to the best prescores overall: percentiles equalize the
    scales of the families, not their volumes.

    Args:
        features: Features of every item of the window.
        prescores: Prescore of every item.
        shown: Items already shown in a previous digest.
        cfg: The triage configuration.

    Returns:
        The candidates, best prescore first.
    """
    eligible = [
        f
        for f in _ranked(features, prescores)
        if f.relevance >= cfg.relevance_gate and (f.item_id not in shown or f.revenant)
    ]
    chosen: set[ItemId] = set()
    for family in FAMILIES:
        in_family = [f.item_id for f in eligible if f.family == family]
        chosen.update(in_family[: cfg.family_floor])
    for f in eligible:
        if len(chosen) >= cfg.candidates:
            break
        chosen.add(f.item_id)
    return tuple(f.item_id for f in eligible if f.item_id in chosen)


def pick_discoveries(
    features: Sequence[FeatureVector], shown: frozenset[ItemId], cfg: TriageConfig
) -> tuple[ItemId, ...]:
    """Pick very popular items outside the profile, at most one per family.

    Args:
        features: Features of every item of the window.
        shown: Items already shown in a previous digest.
        cfg: The triage configuration.

    Returns:
        Up to `discovery.slots` items, most popular first.
    """
    eligible = sorted(
        (
            f
            for f in features
            if f.relevance < cfg.relevance_gate
            and f.popularity >= cfg.discovery.min_popularity
            and f.item_id not in shown
        ),
        key=lambda f: (-f.popularity, f.item_id),
    )
    picked: list[ItemId] = []
    families: set[str] = set()
    for f in eligible:
        if len(picked) >= cfg.discovery.slots:
            break
        if f.family not in families:
            families.add(f.family)
            picked.append(f.item_id)
    return tuple(picked)


def display_theme(item: ScoredItem, weights: Mapping[ThemeId, float]) -> ThemeId | None:
    """Choose the theme an item is listed under in the digest.

    Args:
        item: The scored item.
        weights: Weight of each theme.

    Returns:
        The theme maximizing `weight x LLM relevance`, or `weight x percentile` for an item
        the LLM did not triage; None if no theme applies.
    """
    scores = (
        {t: weights.get(t, 0.0) * s for t, s in item.verdict.scores().items()}
        if item.verdict is not None
        else {t: weights.get(t, 0.0) * p for t, p in item.features.theme_percentile.items()}
    )
    if not scores:
        return None
    return max(sorted(scores), key=lambda t: scores[t])


def passes_llm_gate(item: ScoredItem, llm_gate: int) -> bool:
    """Tell whether the LLM found an item relevant enough (untriaged items pass).

    Args:
        item: The scored item.
        llm_gate: Items whose best LLM relevance is at most this are dropped.

    Returns:
        True if the item may be selected.
    """
    if item.verdict is None:
        return True
    return max(item.verdict.scores().values(), default=0) > llm_gate


def final_selection(
    scored: Sequence[ScoredItem], weights: Mapping[ThemeId, float], cfg: TriageConfig
) -> tuple[ScoredItem, ...]:
    """Select the items of the digest among scored candidates.

    Discoveries are kept as they are; the others must pass the LLM gate and are taken by
    final score within the per-theme and total quotas. Nothing pads a short selection.

    Args:
        scored: Every candidate, with its final score.
        weights: Weight of each theme.
        cfg: The triage configuration.

    Returns:
        Every candidate, with `slot` and `theme` set on the selected ones.
    """
    updates: dict[ItemId, ScoredItem] = {}
    per_theme: Counter[ThemeId] = Counter()
    ranked = sorted(scored, key=lambda s: (-(s.final_score or 0.0), s.item_id))
    for item in ranked:
        theme = display_theme(item, weights)
        if item.discovery:
            updates[item.item_id] = item.model_copy(update={"slot": "discovery", "theme": theme})
            continue
        if theme is None or not passes_llm_gate(item, cfg.llm_gate):
            continue
        taken = sum(per_theme.values())
        if taken >= cfg.selected or per_theme[theme] >= cfg.per_theme_max:
            continue
        per_theme[theme] += 1
        updates[item.item_id] = item.model_copy(update={"slot": "theme", "theme": theme})
    return tuple(updates.get(item.item_id, item) for item in scored)
