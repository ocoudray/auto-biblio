import pytest
import yaml
from pydantic import ValidationError

from auto_biblio.repo_config.sources import (
    ArxivSourceConfig,
    GithubReleasesSourceConfig,
    GithubSearchSourceConfig,
    HackernewsSourceConfig,
    HfPapersSourceConfig,
    RssSourceConfig,
    SourcesConfig,
)

ALL_TYPES = """
sources:
  - {name: arxiv, type: arxiv, categories: [cs.CL]}
  - {name: hf-papers, type: hf_papers}
  - {name: github-rising, type: github_search, topics: [llm]}
  - {name: github-releases, type: github_releases}
  - {name: hn, type: hackernews}
  - {name: blog, type: rss, url: "https://example.com/feed.xml", family: applied}
"""


def parse(text: str) -> SourcesConfig:
    return SourcesConfig.model_validate(yaml.safe_load(text))


def test_sources_discriminated_union() -> None:
    types = [type(s) for s in parse(ALL_TYPES).sources]
    assert types == [
        ArxivSourceConfig,
        HfPapersSourceConfig,
        GithubSearchSourceConfig,
        GithubReleasesSourceConfig,
        HackernewsSourceConfig,
        RssSourceConfig,
    ]


def test_sources_defaults() -> None:
    arxiv, hf, search, _, hn, rss = parse(ALL_TYPES).sources
    assert isinstance(arxiv, ArxivSourceConfig)
    assert (arxiv.max_results, arxiv.min_interval_s, arxiv.overlap_days) == (6000, 5.0, 5)
    assert hf.overlap_days == 2
    assert isinstance(search, GithubSearchSourceConfig)
    assert (search.min_stars, search.created_within_days) == (50, 30)
    assert isinstance(hn, HackernewsSourceConfig)
    assert hn.min_points == 30
    assert hf.enabled is True
    assert rss.min_interval_s == 1.0


def test_sources_reject_duplicate_names() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        parse("sources: [{name: a, type: hf_papers}, {name: a, type: hackernews}]")


def test_unknown_source_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse("sources: [{name: a, type: mastodon}]")


def test_arxiv_requires_categories() -> None:
    with pytest.raises(ValidationError):
        parse("sources: [{name: a, type: arxiv, categories: []}]")
