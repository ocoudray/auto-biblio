"""Generic RSS/Atom connector: blogs, newsletters, subreddits."""

from datetime import datetime
from urllib.parse import urljoin

import httpx

from auto_biblio.domain.ids import canonical_id, kind_for
from auto_biblio.domain.models import Clock, Item, Sighting, SourceBatch
from auto_biblio.repo_config.sources import RssSourceConfig
from auto_biblio.sources._feeds import FeedEntry, parse_feed
from auto_biblio.sources._http import Throttle, get


class RssSource:
    """Poll one feed and turn its recent entries into items."""

    def __init__(
        self, config: RssSourceConfig, client: httpx.Client, clock: Clock, throttle: Throttle
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
        """Fetch entries published since `since`; undated entries are always kept.

        Args:
            since: Aware UTC lower bound.

        Returns:
            The items found (no signals: feeds carry none).
        """
        self._throttle.wait()
        response = get(self._client, str(self._config.url), source=self.name)
        entries = parse_feed(response.content, source=self.name)
        now = self._clock()
        return SourceBatch(
            items=tuple(
                self._item(e, now) for e in entries if e.published is None or e.published >= since
            )
        )

    def _item(self, entry: FeedEntry, now: datetime) -> Item:
        link = urljoin(str(self._config.url), entry.link)
        item_id = canonical_id(link)
        return Item(
            id=item_id,
            kind=kind_for(item_id, "blog_post"),
            title=entry.title,
            summary=entry.summary,
            url=link,  # pyright: ignore[reportArgumentType] - pydantic validates to HttpUrl
            authors=entry.authors,
            published_at=entry.published,
            first_seen=now,
            sightings=(
                Sighting(source=self.name, source_type="rss", seen_at=now, origin_url=link),
            ),
            tags=entry.categories,
        )
