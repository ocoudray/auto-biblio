"""Interest profile: the themes that decide what is relevant."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]
RepoName = Annotated[str, StringConstraints(pattern=r"^[\w.-]+/[\w.-]+$")]


class Watch(BaseModel):
    """Repositories and authors followed explicitly for a theme."""

    model_config = ConfigDict(frozen=True)

    repos: tuple[RepoName, ...] = ()
    authors: tuple[str, ...] = ()


class Theme(BaseModel):
    """One area of interest."""

    model_config = ConfigDict(frozen=True)

    id: Slug
    label: str
    weight: float = Field(default=1.0, ge=0)
    description: str
    keywords: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    watch: Watch = Watch()


class Profile(BaseModel):
    """The full interest profile."""

    model_config = ConfigDict(frozen=True)

    themes: tuple[Theme, ...] = Field(min_length=1)
    global_exclude: tuple[str, ...] = ()

    @field_validator("themes")
    @classmethod
    def _unique_ids(cls, themes: tuple[Theme, ...]) -> tuple[Theme, ...]:
        ids = [theme.id for theme in themes]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            msg = f"duplicate theme ids: {', '.join(duplicates)}"
            raise ValueError(msg)
        return themes

    def watched_repos(self) -> tuple[str, ...]:
        """List every watched repository, lowercased, unique and sorted.

        Returns:
            ``owner/repo`` names.
        """
        return tuple(sorted({repo.lower() for t in self.themes for repo in t.watch.repos}))
