"""Navigation of the site."""

from pydantic import BaseModel, ConfigDict


class NavEntry(BaseModel):
    """One entry of the navigation: a page, or a section of entries."""

    model_config = ConfigDict(frozen=True)

    title: str
    path: str | None = None
    children: tuple["NavEntry", ...] = ()
