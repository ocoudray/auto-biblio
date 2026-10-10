"""Source configuration: one entry per source instance, discriminated by `type`."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from auto_biblio.repo_config.profile import Slug


class _BaseSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Slug
    enabled: bool = True
    min_interval_s: float = Field(default=1.0, ge=0)


class ArxivSourceConfig(_BaseSourceConfig):
    """arXiv export API, filtered by categories."""

    type: Literal["arxiv"]
    categories: tuple[str, ...] = Field(min_length=1)
    max_results: int = Field(default=2000, gt=0)
    min_interval_s: float = Field(default=3.0, ge=0)


class HfPapersSourceConfig(_BaseSourceConfig):
    """Hugging Face daily papers."""

    type: Literal["hf_papers"]


class GithubSearchSourceConfig(_BaseSourceConfig):
    """Recently created, fast-rising GitHub repositories, one search per topic."""

    type: Literal["github_search"]
    topics: tuple[str, ...] = Field(min_length=1)
    min_stars: int = Field(default=50, ge=0)
    created_within_days: int = Field(default=30, gt=0)


class GithubReleasesSourceConfig(_BaseSourceConfig):
    """Releases of the repositories watched in the profile."""

    type: Literal["github_releases"]


class HackernewsSourceConfig(_BaseSourceConfig):
    """Hacker News stories above a points threshold."""

    type: Literal["hackernews"]
    min_points: int = Field(default=30, ge=0)


class RssSourceConfig(_BaseSourceConfig):
    """Any RSS or Atom feed (blogs, newsletters, subreddits)."""

    type: Literal["rss"]
    url: HttpUrl
    family: Literal["academic", "applied", "community"]


SourceConfig = Annotated[
    ArxivSourceConfig
    | HfPapersSourceConfig
    | GithubSearchSourceConfig
    | GithubReleasesSourceConfig
    | HackernewsSourceConfig
    | RssSourceConfig,
    Field(discriminator="type"),
]


class SourcesConfig(BaseModel):
    """All configured sources."""

    model_config = ConfigDict(frozen=True)

    sources: tuple[SourceConfig, ...]

    @field_validator("sources")
    @classmethod
    def _unique_names(cls, sources: tuple[SourceConfig, ...]) -> tuple[SourceConfig, ...]:
        names = [s.name for s in sources]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            msg = f"duplicate source names: {', '.join(duplicates)}"
            raise ValueError(msg)
        return sources
