"""arXiv connector: latest submissions in the configured categories."""

from datetime import datetime

import httpx

from auto_biblio.domain.ids import canonical_id
from auto_biblio.domain.models import Clock, Item, Sighting, SourceBatch
from auto_biblio.repo_config.sources import ArxivSourceConfig
from auto_biblio.sources._feeds import FeedEntry, parse_feed
from auto_biblio.sources._http import Throttle, get

API_URL = "https://export.arxiv.org/api/query"
PAGE_SIZE = 100


class ArxivSource:
    """Page through the arXiv export API, newest first, until `since` is reached."""

    def __init__(
        self, config: ArxivSourceConfig, client: httpx.Client, clock: Clock, throttle: Throttle
    ) -> None:
        """Build the connector.

        Args:
            config: Source configuration.
            client: Injected HTTP client.
            clock: Current time provider.
            throttle: Request pacing (arXiv asks for 3 s between calls).
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
        """Fetch papers submitted since `since`, at most `max_results` of them.

        Args:
            since: Aware UTC lower bound.

        Returns:
            The papers found.
        """
        query = " OR ".join(f"cat:{c}" for c in self._config.categories)
        entries: list[FeedEntry] = []
        while len(entries) < self._config.max_results:
            page = self._page(query, start=len(entries))
            recent = [e for e in page if e.published is None or e.published >= since]
            entries.extend(recent)
            if not page or len(recent) < len(page):
                break
        now = self._clock()
        return SourceBatch(items=tuple(self._item(e, now) for e in entries))

    def _page(self, query: str, start: int) -> tuple[FeedEntry, ...]:
        self._throttle.wait()
        size = min(PAGE_SIZE, self._config.max_results - start)
        params: dict[str, str | int] = {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": size,
        }
        response = get(self._client, API_URL, source=self.name, params=params)
        return parse_feed(response.content, source=self.name)[:size]

    def _item(self, entry: FeedEntry, now: datetime) -> Item:
        item_id = canonical_id(entry.link)
        url = f"https://arxiv.org/abs/{item_id.removeprefix('arxiv:')}"
        return Item(
            id=item_id,
            kind="paper",
            title=entry.title,
            summary=entry.summary,
            url=url,  # pyright: ignore[reportArgumentType] - pydantic validates to HttpUrl
            authors=entry.authors,
            published_at=entry.published,
            first_seen=now,
            sightings=(
                Sighting(source=self.name, source_type="arxiv", seen_at=now, origin_url=entry.link),
            ),
            tags=tuple(sorted(entry.categories)),
        )
