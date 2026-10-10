import httpx
from builders import NOW
from pydantic import SecretStr

from auto_biblio.config import Settings
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.repo_config.profile import Profile, Theme, Watch
from auto_biblio.repo_config.sources import SourcesConfig
from auto_biblio.sources import build_sources
from auto_biblio.sources.arxiv import ArxivSource
from auto_biblio.sources.github import GithubReleasesSource, GithubSearchSource
from auto_biblio.sources.hackernews import HackernewsSource
from auto_biblio.sources.hf_papers import HfPapersSource
from auto_biblio.sources.rss import RssSource


def make_config() -> RepoConfig:
    sources = SourcesConfig.model_validate(
        {
            "sources": [
                {"name": "arxiv", "type": "arxiv", "categories": ["cs.CL"]},
                {"name": "hf", "type": "hf_papers"},
                {"name": "rising", "type": "github_search", "topics": ["llm"]},
                {"name": "releases", "type": "github_releases"},
                {"name": "hn", "type": "hackernews"},
                {"name": "blog", "type": "rss", "url": "https://e.com/f", "family": "applied"},
                {
                    "name": "off",
                    "type": "rss",
                    "url": "https://e.com/g",
                    "family": "applied",
                    "enabled": False,
                },
            ]
        }
    )
    theme = Theme(id="t", label="t", description="d", watch=Watch(repos=("astral-sh/uv",)))
    return RepoConfig(profile=Profile(themes=(theme,)), sources=sources)


def test_build_sources_types_and_enabled() -> None:
    settings = Settings(_env_file=None, github_token=SecretStr("t"))  # pyright: ignore[reportCallIssue]
    with httpx.Client() as client:
        sources = build_sources(make_config(), settings, client, lambda: NOW)
    assert [type(s) for s in sources] == [
        ArxivSource,
        HfPapersSource,
        GithubSearchSource,
        GithubReleasesSource,
        HackernewsSource,
        RssSource,
    ]
    assert [s.name for s in sources] == ["arxiv", "hf", "rising", "releases", "hn", "blog"]


def test_releases_receive_watched_repos() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    with httpx.Client() as client:
        releases = build_sources(make_config(), settings, client, lambda: NOW)[3]
    assert isinstance(releases, GithubReleasesSource)
    assert releases.repos == ("astral-sh/uv",)
