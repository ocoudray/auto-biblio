"""Builders for domain objects used across test modules."""

from datetime import UTC, datetime

from auto_biblio.domain.ids import ItemId, ItemKind
from auto_biblio.domain.models import Item, Sighting, Signal, SignalKind, SourceType

NOW = datetime(2026, 10, 10, 5, 0, tzinfo=UTC)


def make_item(  # noqa: PLR0913 - builder mirrors the model's fields
    *,
    item_id: str = "arxiv:2410.12345",
    source_type: SourceType = "arxiv",
    source: str | None = None,
    title: str = "Title",
    summary: str | None = "summary",
    seen_at: datetime = NOW,
    links: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    kind: ItemKind = "paper",
) -> Item:
    """Build an item seen once by one source."""
    return Item(
        id=ItemId(item_id),
        kind=kind,
        title=title,
        summary=summary,
        url="https://example.com/x",  # pyright: ignore[reportArgumentType] - validated to HttpUrl
        authors=("A",),
        published_at=None,
        first_seen=seen_at,
        sightings=(
            Sighting(
                source=source or source_type,
                source_type=source_type,
                seen_at=seen_at,
                origin_url=f"https://{source_type}.example/x",
            ),
        ),
        links=tuple(ItemId(link) for link in links),
        tags=tags,
    )


def make_signal(
    *,
    item_id: str = "gh:o/r",
    kind: SignalKind = "gh_stars",
    value: int = 10,
    observed_at: datetime = NOW,
) -> Signal:
    """Build a signal."""
    return Signal(
        item_id=ItemId(item_id), kind=kind, value=value, observed_at=observed_at, source="s"
    )
