"""Core data model: items, where they were seen, and the signals observed about them."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl, field_validator

from auto_biblio.domain.ids import ItemId, ItemKind

__all__ = [
    "Clock",
    "Item",
    "ItemKind",
    "Sighting",
    "Signal",
    "SignalKind",
    "SourceBatch",
    "SourceType",
]

Clock = Callable[[], datetime]
"""Returns the current time as an aware UTC datetime (injected for testability)."""

SourceType = Literal["arxiv", "hf_papers", "github_search", "github_releases", "hackernews", "rss"]
SignalKind = Literal["gh_stars", "hf_upvotes", "hn_points", "hn_comments"]


class Sighting(BaseModel):
    """One observation of an item by a source."""

    model_config = ConfigDict(frozen=True)

    source: str
    source_type: SourceType
    seen_at: AwareDatetime
    origin_url: str


class Item(BaseModel):
    """A piece of content (paper, repository, release, post, discussion), deduplicated."""

    model_config = ConfigDict(frozen=True)

    id: ItemId
    kind: ItemKind
    title: str
    summary: str | None
    url: HttpUrl
    authors: tuple[str, ...]
    published_at: AwareDatetime | None
    first_seen: AwareDatetime
    sightings: tuple[Sighting, ...]
    links: tuple[ItemId, ...] = ()
    tags: tuple[str, ...] = ()

    @field_validator("sightings")
    @classmethod
    def _at_least_one_sighting(cls, value: tuple[Sighting, ...]) -> tuple[Sighting, ...]:
        if not value:
            msg = "an item needs at least one sighting"
            raise ValueError(msg)
        return value

    @field_validator("links", "tags")
    @classmethod
    def _sorted_unique[T: str](cls, value: tuple[T, ...]) -> tuple[T, ...]:
        # A canonical order makes equal items serialize identically, which keeps
        # the stores idempotent whatever order the sources return.
        return tuple(sorted(set(value)))


class Signal(BaseModel):
    """A numeric popularity observation about an item at a point in time."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    kind: SignalKind
    value: int
    observed_at: AwareDatetime
    source: str


class SourceBatch(BaseModel):
    """Everything one source returned during one fetch."""

    model_config = ConfigDict(frozen=True)

    items: tuple[Item, ...] = ()
    signals: tuple[Signal, ...] = ()
