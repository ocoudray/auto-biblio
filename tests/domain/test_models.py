from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Sighting, Signal, SourceBatch

NOW = datetime(2026, 10, 10, 5, 0, tzinfo=UTC)


def make_sighting() -> Sighting:
    return Sighting(
        source="arxiv", source_type="arxiv", seen_at=NOW, origin_url="https://arxiv.org/abs/1"
    )


def test_item_requires_sighting() -> None:
    with pytest.raises(ValidationError, match="sighting"):
        Item(
            id=ItemId("arxiv:2410.12345"),
            kind="paper",
            title="T",
            summary=None,
            url="https://arxiv.org/abs/2410.12345",  # pyright: ignore[reportArgumentType]
            authors=(),
            published_at=None,
            first_seen=NOW,
            sightings=(),
        )


def test_item_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        Item(
            id=ItemId("arxiv:2410.12345"),
            kind="paper",
            title="T",
            summary=None,
            url="https://arxiv.org/abs/2410.12345",  # pyright: ignore[reportArgumentType]
            authors=(),
            published_at=datetime(2026, 10, 1),  # noqa: DTZ001 - the naive date is the point
            first_seen=NOW,
            sightings=(make_sighting(),),
        )


def test_signal_and_batch_defaults() -> None:
    signal = Signal(
        item_id=ItemId("gh:o/r"), kind="gh_stars", value=10, observed_at=NOW, source="gh"
    )
    assert SourceBatch().items == ()
    assert SourceBatch(signals=(signal,)).signals == (signal,)


def test_item_normalizes_tags_and_links() -> None:
    item = Item(
        id=ItemId("url:0000000000000001"),
        kind="blog_post",
        title="T",
        summary=None,
        url="https://e.com/x",  # pyright: ignore[reportArgumentType]
        authors=(),
        published_at=None,
        first_seen=NOW,
        sightings=(make_sighting(),),
        links=(ItemId("gh:b/b"), ItemId("gh:a/a"), ItemId("gh:b/b")),
        tags=("llms", "ai", "llms"),
    )
    assert item.tags == ("ai", "llms")
    assert item.links == ("gh:a/a", "gh:b/b")
