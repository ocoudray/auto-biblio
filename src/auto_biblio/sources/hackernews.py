"""Hacker News connector (Algolia search API): community buzz around links and discussions."""

from datetime import datetime

import httpx
from pydantic import BaseModel, TypeAdapter

from auto_biblio.domain.ids import canonical_id, kind_for
from auto_biblio.domain.models import Clock, Item, Sighting, Signal, SignalKind, SourceBatch
from auto_biblio.repo_config.sources import HackernewsSourceConfig
from auto_biblio.sources._http import Throttle, get, parse_json

API_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://news.ycombinator.com/item?id={}"
HITS_PER_PAGE = 1000


class _Hit(BaseModel):
    objectID: str  # noqa: N815 - mirrors the API field name
    title: str
    url: str | None = None
    points: int = 0
    num_comments: int | None = None
    created_at_i: int


class _Result(BaseModel):
    hits: list[_Hit]


_RESULT = TypeAdapter(_Result)


class HackernewsSource:
    """Fetch stories above a points threshold posted since `since`."""

    def __init__(
        self, config: HackernewsSourceConfig, client: httpx.Client, clock: Clock, throttle: Throttle
    ) -> None:
        """Build the connector.

        Args:
            config: Source configuration.
            client: Injected HTTP client.
            clock: Current time provider.
            throttle: Request pacing.
        """
        self._config = config
        self._client = client
        self._clock = clock
        self._throttle = throttle

    @property
    def name(self) -> str:
        """Configured name of this source instance."""
        return self._config.name

    def fetch(self, since: datetime) -> SourceBatch:
        """Fetch stories posted since `since`.

        A story's item is the content it links to (an arXiv link becomes the
        paper); a story without a link is a discussion.

        Args:
            since: Aware UTC lower bound.

        Returns:
            Items, plus their points and comment counts.
        """
        self._throttle.wait()
        filters = f"created_at_i>{int(since.timestamp())},points>{self._config.min_points}"
        params: dict[str, str | int] = {
            "tags": "story",
            "numericFilters": filters,
            "hitsPerPage": HITS_PER_PAGE,
        }
        response = get(
            self._client, API_URL, source=self.name, params=params, throttle=self._throttle
        )
        now = self._clock()
        items: list[Item] = []
        signals: list[Signal] = []
        for hit in parse_json(response, _RESULT, source=self.name).hits:
            item = self._item(hit, now)
            items.append(item)
            signals.extend(self._signals(item, hit, now))
        return SourceBatch(items=tuple(items), signals=tuple(signals))

    def _item(self, hit: _Hit, now: datetime) -> Item:
        discussion_url = ITEM_URL.format(hit.objectID)
        target = hit.url or discussion_url
        item_id = canonical_id(target)
        return Item(
            id=item_id,
            kind=kind_for(item_id, "blog_post") if hit.url else "discussion",
            title=hit.title,
            summary=None,
            url=target,  # pyright: ignore[reportArgumentType] - pydantic validates to HttpUrl
            authors=(),
            published_at=None,
            first_seen=now,
            sightings=(
                Sighting(
                    source=self.name,
                    source_type="hackernews",
                    seen_at=now,
                    origin_url=discussion_url,
                ),
            ),
        )

    def _signals(self, item: Item, hit: _Hit, now: datetime) -> list[Signal]:
        values: tuple[tuple[SignalKind, int], ...] = (
            ("hn_points", hit.points),
            ("hn_comments", hit.num_comments or 0),
        )
        return [
            Signal(item_id=item.id, kind=kind, value=value, observed_at=now, source=self.name)
            for kind, value in values
        ]
