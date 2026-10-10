"""Hugging Face Daily Papers connector: community-curated papers with upvotes."""

from datetime import date, datetime, timedelta

import httpx
from pydantic import AwareDatetime, BaseModel, TypeAdapter

from auto_biblio.domain.ids import ItemId, canonical_id
from auto_biblio.domain.models import Clock, Item, Sighting, Signal, SourceBatch
from auto_biblio.repo_config.sources import HfPapersSourceConfig
from auto_biblio.sources._http import Throttle, get, parse_json

API_URL = "https://huggingface.co/api/daily_papers"


class _HfAuthor(BaseModel):
    name: str


class _HfPaper(BaseModel):
    id: str
    title: str
    summary: str | None = None
    authors: list[_HfAuthor] = []
    publishedAt: AwareDatetime | None = None  # noqa: N815 - mirrors the API field name
    upvotes: int = 0
    githubRepo: str | None = None  # noqa: N815 - mirrors the API field name


class _HfDailyPaper(BaseModel):
    paper: _HfPaper


_DAY = TypeAdapter(list[_HfDailyPaper])


class HfPapersSource:
    """Fetch the daily papers list for each day since `since`."""

    def __init__(
        self, config: HfPapersSourceConfig, client: httpx.Client, clock: Clock, throttle: Throttle
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
        """Fetch every daily list from `since`'s day to today, deduplicated.

        Args:
            since: Aware UTC lower bound.

        Returns:
            Papers, linked to their code repository, and their upvotes.
        """
        now = self._clock()
        papers: dict[str, _HfPaper] = {}
        for day in _days(since.date(), now.date()):
            for entry in self._day(day):
                papers.setdefault(entry.paper.id, entry.paper)
        items = tuple(self._item(p, now) for p in papers.values())
        signals = tuple(
            Signal(
                item_id=item.id,
                kind="hf_upvotes",
                value=p.upvotes,
                observed_at=now,
                source=self.name,
            )
            for item, p in zip(items, papers.values(), strict=True)
        )
        return SourceBatch(items=items, signals=signals)

    def _day(self, day: date) -> list[_HfDailyPaper]:
        self._throttle.wait()
        response = get(
            self._client,
            API_URL,
            source=self.name,
            params={"date": day.isoformat()},
            throttle=self._throttle,
        )
        return parse_json(response, _DAY, source=self.name)

    def _item(self, paper: _HfPaper, now: datetime) -> Item:
        url = f"https://huggingface.co/papers/{paper.id}"
        links = (canonical_id(paper.githubRepo),) if paper.githubRepo else ()
        return Item(
            id=ItemId(f"arxiv:{paper.id}"),
            kind="paper",
            title=" ".join(paper.title.split()),
            summary=paper.summary,
            url=url,  # pyright: ignore[reportArgumentType] - pydantic validates to HttpUrl
            authors=tuple(a.name for a in paper.authors),
            published_at=paper.publishedAt,
            first_seen=now,
            sightings=(
                Sighting(source=self.name, source_type="hf_papers", seen_at=now, origin_url=url),
            ),
            links=links,
        )


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]
