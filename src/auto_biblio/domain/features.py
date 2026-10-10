"""Per-item features of the triage, on scales comparable across sources."""

from collections import defaultdict
from collections.abc import Hashable, Mapping, Sequence
from typing import Literal, NewType, get_args

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, SourceType

ThemeId = NewType("ThemeId", str)
SourceFamily = Literal["paper", "repo", "discussion", "feed"]
ContextLevel = Literal["title_only", "snippet", "abstract"]

FAMILIES: tuple[SourceFamily, ...] = get_args(SourceFamily)
CONTEXT_LEVELS: tuple[ContextLevel, ...] = get_args(ContextLevel)

FAMILY_OF: Mapping[SourceType, SourceFamily] = {
    "arxiv": "paper",
    "hf_papers": "paper",
    "github_search": "repo",
    "github_releases": "repo",
    "hackernews": "discussion",
    "rss": "feed",
}
FAMILY_PRIORITY: tuple[SourceFamily, ...] = ("paper", "repo", "feed", "discussion")
"""When several families provided text, the item is compared within the first one."""


def item_family(item: Item) -> SourceFamily:
    """Return the family an item is compared within.

    An item with a summary belongs to the highest-priority family that saw it, since the
    richer sources are the ones that provide text. A title-only item keeps the family of
    its first sighting.

    Args:
        item: The item.

    Returns:
        Its source family.
    """
    if item.summary:
        seen = families_seen(item)
        return next(family for family in FAMILY_PRIORITY if family in seen)
    return FAMILY_OF[item.sightings[0].source_type]


def families_seen(item: Item) -> frozenset[SourceFamily]:
    """Return every family that saw an item.

    Args:
        item: The item.

    Returns:
        The distinct families of its sightings.
    """
    return frozenset(FAMILY_OF[s.source_type] for s in item.sightings)


def multi_source(source_count: int) -> float:
    """Score how widely an item was seen, saturating at three families.

    Args:
        source_count: Number of distinct families that saw the item.

    Returns:
        0 for one family, 0.5 for two, 1 for three or more.
    """
    return min(source_count - 1, 2) / 2


def embedding_text(item: Item, max_words: int) -> str:
    """Build the text embedded for an item: same shape whatever the source.

    Args:
        item: The item.
        max_words: How many words of the summary to keep after the title.

    Returns:
        `<title> — <first words of the summary>`, or the title alone.
    """
    title = " ".join(item.title.split())
    words = (item.summary or "").split()[:max_words]
    return f"{title} — {' '.join(words)}" if words else title


def context_level(item: Item, snippet: str | None) -> ContextLevel:
    """Tell how much text the LLM will see for an item.

    Args:
        item: The item.
        snippet: Context fetched for an item without summary, if any.

    Returns:
        The context level.
    """
    if item.summary:
        return "abstract"
    return "snippet" if snippet else "title_only"


def percentile_ranks(values: Sequence[float]) -> list[float]:
    """Rank values on [0, 1], ties sharing their average rank.

    Args:
        values: Any values.

    Returns:
        `(rank - 1) / (n - 1)` for each value; a single value gets 0.5.
    """
    n = len(values)
    if n == 1:
        return [0.5]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    start = 0
    while start < n:
        end = start
        while end + 1 < n and values[order[end + 1]] == values[order[start]]:
            end += 1
        average = (start + end) / 2
        for position in range(start, end + 1):
            ranks[order[position]] = average / (n - 1)
        start = end + 1
    return ranks


def percentile_of(value: float, population: Sequence[float]) -> float:
    """Rank a value against a population, with the convention of `percentile_ranks`.

    Args:
        value: The value to rank; it need not belong to the population.
        population: The reference values.

    Returns:
        The share of the population below the value, ties counting half, on [0, 1].
    """
    if not population:
        return 0.5
    below = sum(1 for other in population if other < value)
    equal = sum(1 for other in population if other == value)
    return (below + equal / 2) / len(population)


def grouped_percentiles[K: Hashable, G: Hashable](
    values: Mapping[K, float], groups: Mapping[K, G], min_population: int
) -> dict[K, float]:
    """Rank values within their group, falling back to all values for small groups.

    Args:
        values: The value of each key.
        groups: The group of each key.
        min_population: Groups smaller than this are ranked against every value.

    Returns:
        The percentile of each key.
    """
    members: defaultdict[G, list[K]] = defaultdict(list)
    for key in values:
        members[groups[key]].append(key)
    every = list(values)
    result: dict[K, float] = {}
    global_ranks = dict(zip(every, percentile_ranks([values[k] for k in every]), strict=True))
    for keys in members.values():
        if len(keys) < min_population:
            result.update({k: global_ranks[k] for k in keys})
            continue
        result.update(zip(keys, percentile_ranks([values[k] for k in keys]), strict=True))
    return result


class FeatureVector(BaseModel):
    """Everything the scoring knows about an item, on scales comparable across sources."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    family: SourceFamily
    context_level: ContextLevel
    theme_similarity: dict[ThemeId, float]
    """Raw cosine similarity with each theme, kept for diagnosis."""
    theme_percentile: dict[ThemeId, float]
    """Rank of the similarity within the item's family, on [0, 1]."""
    relevance: float
    popularity: float
    source_count: int
    watched: bool
    revenant: bool
    age_days: float

    def model_inputs(self, llm_rel: float | None) -> dict[str, float]:
        """Return the inputs of the scoring models, in a stable order.

        Args:
            llm_rel: Relevance given by the LLM on [0, 1], None if the LLM did not triage.

        Returns:
            Named numeric inputs, with an `unverified` indicator and one indicator per family
            and per context level.
        """
        inputs = {
            "relevance": self.relevance,
            "popularity": self.popularity,
            "multi_source": multi_source(self.source_count),
            "watched": float(self.watched),
            "revenant": float(self.revenant),
            "llm_rel": llm_rel or 0.0,
            "unverified": float(llm_rel is None),
        }
        inputs.update({f"family_{f}": float(self.family == f) for f in FAMILIES})
        inputs.update({f"context_{c}": float(self.context_level == c) for c in CONTEXT_LEVELS})
        return inputs
