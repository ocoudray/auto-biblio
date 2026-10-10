"""GitHub connectors: fast-rising new repositories and releases of watched repositories."""

import logging
from datetime import datetime, timedelta
from http import HTTPStatus

import httpx
from pydantic import AwareDatetime, BaseModel, SecretStr, TypeAdapter

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.domain.ids import ItemId, canonical_id
from auto_biblio.domain.models import Clock, Item, Sighting, Signal, SourceBatch
from auto_biblio.repo_config.sources import GithubReleasesSourceConfig, GithubSearchSourceConfig
from auto_biblio.sources._feeds import SUMMARY_MAX
from auto_biblio.sources._http import Throttle, get, parse_json

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
SEARCH_PAGE_SIZE = 100
RELEASES_PAGE_SIZE = 30


class _Repo(BaseModel):
    full_name: str
    html_url: str
    description: str | None = None
    stargazers_count: int
    created_at: AwareDatetime
    topics: list[str] = []


class _SearchResult(BaseModel):
    items: list[_Repo]


class _Release(BaseModel):
    tag_name: str
    name: str | None = None
    html_url: str
    published_at: AwareDatetime | None = None
    draft: bool = False
    body: str | None = None


_SEARCH = TypeAdapter(_SearchResult)
_RELEASES = TypeAdapter(list[_Release])


def _headers(token: SecretStr | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token.get_secret_value()}"
    return headers


class GithubSearchSource:
    """Search recently created repositories above a star threshold, one query per topic."""

    def __init__(
        self,
        config: GithubSearchSourceConfig,
        client: httpx.Client,
        clock: Clock,
        throttle: Throttle,
        *,
        token: SecretStr | None,
    ) -> None:
        """Build the connector.

        Args:
            config: Source configuration.
            client: Injected HTTP client.
            clock: Current time provider.
            throttle: Request pacing.
            token: Optional GitHub token (raises the rate limit).
        """
        self._config = config
        self._client = client
        self._clock = clock
        self._throttle = throttle
        self._headers = _headers(token)

    @property
    def name(self) -> str:
        """Configured name of this source instance."""
        return self._config.name

    def fetch(self, since: datetime) -> SourceBatch:  # noqa: ARG002 - window is created_within_days
        """Fetch rising repositories; the window is `created_within_days`, not `since`.

        Args:
            since: Ignored: "rising" is defined by creation date and stars.

        Returns:
            Repositories and their star counts.
        """
        now = self._clock()
        created_after = (now - timedelta(days=self._config.created_within_days)).date()
        repos: dict[str, _Repo] = {}
        for topic in self._config.topics:
            query = f"topic:{topic} created:>{created_after} stars:>{self._config.min_stars}"
            for repo in self._search(query):
                repos.setdefault(repo.full_name.lower(), repo)
        items = tuple(self._item(r, now) for r in repos.values())
        signals = tuple(
            Signal(
                item_id=item.id,
                kind="gh_stars",
                value=repo.stargazers_count,
                observed_at=now,
                source=self.name,
            )
            for item, repo in zip(items, repos.values(), strict=True)
        )
        return SourceBatch(items=items, signals=signals)

    def _search(self, query: str) -> list[_Repo]:
        self._throttle.wait()
        params: dict[str, str | int] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": SEARCH_PAGE_SIZE,
        }
        response = get(
            self._client,
            f"{API_URL}/search/repositories",
            source=self.name,
            params=params,
            headers=self._headers,
        )
        return parse_json(response, _SEARCH, source=self.name).items

    def _item(self, repo: _Repo, now: datetime) -> Item:
        return Item(
            id=canonical_id(repo.html_url),
            kind="repo",
            title=repo.full_name,
            summary=repo.description,
            url=repo.html_url,  # pyright: ignore[reportArgumentType] - pydantic validates to HttpUrl
            authors=(repo.full_name.split("/")[0],),
            published_at=repo.created_at,
            first_seen=now,
            sightings=(
                Sighting(
                    source=self.name,
                    source_type="github_search",
                    seen_at=now,
                    origin_url=repo.html_url,
                ),
            ),
            tags=tuple(sorted(repo.topics)),
        )


class GithubReleasesSource:
    """List the latest releases of each watched repository."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        config: GithubReleasesSourceConfig,
        repos: tuple[str, ...],
        client: httpx.Client,
        clock: Clock,
        throttle: Throttle,
        *,
        token: SecretStr | None,
    ) -> None:
        """Build the connector.

        Args:
            config: Source configuration.
            repos: Watched ``owner/repo`` names (from the profile).
            client: Injected HTTP client.
            clock: Current time provider.
            throttle: Request pacing.
            token: Optional GitHub token (raises the rate limit).
        """
        self._config = config
        self._repos = repos
        self._client = client
        self._clock = clock
        self._throttle = throttle
        self._headers = _headers(token)

    @property
    def name(self) -> str:
        """Configured name of this source instance."""
        return self._config.name

    @property
    def repos(self) -> tuple[str, ...]:
        """Watched ``owner/repo`` names."""
        return self._repos

    def fetch(self, since: datetime) -> SourceBatch:
        """Fetch releases published since `since` (drafts are ignored).

        Args:
            since: Aware UTC lower bound.

        Returns:
            One item per release, linked to its repository.
        """
        now = self._clock()
        items = tuple(
            self._item(repo, release, now)
            for repo in self._repos
            for release in self._releases(repo)
            if release.published_at is not None and release.published_at > since
        )
        return SourceBatch(items=items)

    def _releases(self, repo: str) -> list[_Release]:
        self._throttle.wait()
        try:
            response = get(
                self._client,
                f"{API_URL}/repos/{repo}/releases",
                source=self.name,
                params={"per_page": RELEASES_PAGE_SIZE},
                headers=self._headers,
            )
        except SourceUnavailableError as exc:
            if exc.status_code != HTTPStatus.NOT_FOUND:
                raise
            # A renamed or deleted watched repo must not block the others' releases.
            logger.warning("%s: watched repository %s not found, skipped", self.name, repo)
            return []
        return [r for r in parse_json(response, _RELEASES, source=self.name) if not r.draft]

    def _item(self, repo: str, release: _Release, now: datetime) -> Item:
        return Item(
            id=ItemId(f"gh:{repo.lower()}@{release.tag_name}"),
            kind="release",
            title=f"{repo} {release.name or release.tag_name}",
            summary=release.body[:SUMMARY_MAX] if release.body else None,
            url=release.html_url,  # pyright: ignore[reportArgumentType] - validated to HttpUrl
            authors=(),
            published_at=release.published_at,
            first_seen=now,
            sightings=(
                Sighting(
                    source=self.name,
                    source_type="github_releases",
                    seen_at=now,
                    origin_url=release.html_url,
                ),
            ),
            links=(ItemId(f"gh:{repo.lower()}"),),
        )
