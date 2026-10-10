"""Merge two observations of the same content into one item."""

import re
from collections.abc import Mapping

from auto_biblio.domain.models import Item, Sighting, SourceType

SOURCE_PRIORITY: Mapping[SourceType, int] = {
    "arxiv": 0,
    "hf_papers": 1,
    "github_search": 2,
    "github_releases": 2,
    "rss": 3,
    "hackernews": 4,
}
"""Reliability rank of each source type for descriptive fields (lower wins)."""

_PUNCTUATION = re.compile(r"[^\w\s-]")
_SPACES = re.compile(r"\s+")


def normalized_title(title: str) -> str:
    """Normalize a title for fuzzy identity: lowercase, no punctuation but ``-``, single spaces.

    Args:
        title: Raw title.

    Returns:
        The normalized title.
    """
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", title.lower())).strip()


def merge_items(existing: Item, incoming: Item) -> Item:
    """Merge two observations of the same content.

    Set-like fields are unioned and sorted; ``first_seen`` keeps the earliest
    date; descriptive fields come from the most reliable source and missing
    values are filled from the other item. On a priority tie, ``existing`` wins.

    Args:
        existing: The item already known.
        incoming: The newly observed item.

    Returns:
        The merged item, keeping the identity of ``existing``.

    Raises:
        ValueError: If the two items are not the same content.
    """
    if not _same_content(existing, incoming):
        msg = f"cannot merge different items {existing.id} and {incoming.id}"
        raise ValueError(msg)
    winner, other = (
        (incoming, existing)
        if _best_rank(incoming) < _best_rank(existing)
        else (existing, incoming)
    )
    return Item(
        id=existing.id,
        kind=winner.kind,
        title=winner.title or other.title,
        summary=winner.summary if winner.summary is not None else other.summary,
        url=winner.url,
        authors=winner.authors or other.authors,
        published_at=winner.published_at or other.published_at,
        first_seen=min(existing.first_seen, incoming.first_seen),
        sightings=_merge_sightings(existing.sightings, incoming.sightings),
        links=tuple(sorted({*existing.links, *incoming.links})),
        tags=tuple(sorted({*existing.tags, *incoming.tags})),
    )


def _same_content(a: Item, b: Item) -> bool:
    if a.id == b.id:
        return True
    return a.kind == b.kind == "paper" and normalized_title(a.title) == normalized_title(b.title)


def _best_rank(item: Item) -> int:
    return min(SOURCE_PRIORITY[s.source_type] for s in item.sightings)


def _merge_sightings(
    first: tuple[Sighting, ...], second: tuple[Sighting, ...]
) -> tuple[Sighting, ...]:
    unique: dict[tuple[str, str, object], Sighting] = {}
    for sighting in sorted((*first, *second), key=lambda s: (s.seen_at, s.source)):
        key = (sighting.source, sighting.origin_url, sighting.seen_at.date())
        unique.setdefault(key, sighting)
    return tuple(unique.values())
