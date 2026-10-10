"""Source connectors: fetch raw content from the outside world and normalize it to items."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import httpx

from auto_biblio.config import Settings
from auto_biblio.domain.models import Clock, SourceBatch
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.repo_config.sources import (
    ArxivSourceConfig,
    GithubReleasesSourceConfig,
    GithubSearchSourceConfig,
    HackernewsSourceConfig,
    HfPapersSourceConfig,
    RssSourceConfig,
    SourceConfig,
)
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.arxiv import ArxivSource
from auto_biblio.sources.github import GithubReleasesSource, GithubSearchSource
from auto_biblio.sources.hackernews import HackernewsSource
from auto_biblio.sources.hf_papers import HfPapersSource
from auto_biblio.sources.rss import RssSource


class Source(Protocol):
    """A configured source instance that can be polled for new content."""

    @property
    def name(self) -> str:
        """Configured name of this source instance."""
        ...

    def fetch(self, since: datetime) -> SourceBatch:
        """Fetch what the source published since a point in time.

        Args:
            since: Aware UTC lower bound (sources may return a little more).

        Returns:
            Normalized items and signals.

        Raises:
            SourceUnavailableError: The source could not be reached.
            SourcePayloadError: The source answered with an unexpected payload.
        """
        ...


SourceFactory = Callable[[RepoConfig, Settings, httpx.Client, Clock], list[Source]]
"""Builds the source instances of a run (injected into the CLI, faked in tests)."""


def build_sources(
    config: RepoConfig, settings: Settings, client: httpx.Client, clock: Clock
) -> list[Source]:
    """Instantiate a connector for every enabled source, in configuration order.

    Args:
        config: The data repository configuration.
        settings: Application settings (GitHub token).
        client: Shared HTTP client.
        clock: Current time provider.

    Returns:
        The connectors.
    """
    return [
        _build(source, config, settings, client, clock)
        for source in config.sources.sources
        if source.enabled
    ]


def _build(
    source: SourceConfig,
    config: RepoConfig,
    settings: Settings,
    client: httpx.Client,
    clock: Clock,
) -> Source:
    throttle = Throttle(source.min_interval_s)
    token = settings.github_token
    match source:
        case ArxivSourceConfig():
            return ArxivSource(source, client, clock, throttle)
        case HfPapersSourceConfig():
            return HfPapersSource(source, client, clock, throttle)
        case GithubSearchSourceConfig():
            return GithubSearchSource(source, client, clock, throttle, token=token)
        case GithubReleasesSourceConfig():
            repos = config.profile.watched_repos()
            return GithubReleasesSource(source, repos, client, clock, throttle, token=token)
        case HackernewsSourceConfig():
            return HackernewsSource(source, client, clock, throttle)
        case RssSourceConfig():
            return RssSource(source, client, clock, throttle)
