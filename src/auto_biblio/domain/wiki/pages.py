"""Pages of the wiki: one file per notion, one `index.md` per domain."""

from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auto_biblio.domain.errors import KBFormatError, WikiFormatError
from auto_biblio.domain.kb.markdown import split_front_matter

NOTION_ID = r"^[a-z0-9-]+/[a-z0-9-]+$"
"""A notion is `<domain>/<notion>`, its path in `wiki/` without extension."""

NotionId = Annotated[str, Field(pattern=NOTION_ID)]
INDEX = "index.md"


class NotionMeta(BaseModel):
    """Front-matter of a notion page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    aliases: tuple[str, ...] = ()
    prerequisites: tuple[NotionId, ...] = ()
    related: tuple[NotionId, ...] = ()
    themes: tuple[str, ...] = ()
    updated_at: date


class DomainIndex(BaseModel):
    """Front-matter of a domain `index.md`: its title and reading order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    order: tuple[NotionId, ...]


class Notion(BaseModel):
    """A notion page, read back."""

    model_config = ConfigDict(frozen=True)

    id: str
    meta: NotionMeta
    title: str
    """The `# ` line."""
    summary: str
    """Text between the title and the first `## ` section."""
    headings: tuple[str, ...]
    body: str
    """Everything after the front-matter."""


class Domain(BaseModel):
    """A domain of the wiki."""

    model_config = ConfigDict(frozen=True)

    id: str
    index: DomainIndex
    intro: str


class Wiki(BaseModel):
    """The whole wiki, as read from `wiki/`."""

    model_config = ConfigDict(frozen=True)

    domains: dict[str, Domain] = {}
    notions: dict[str, Notion] = {}
    assets: frozenset[PurePosixPath] = frozenset()
    unreadable: dict[PurePosixPath, str] = {}
    """Pages that could not be read, with the reason."""


def _meta[ModelT: BaseModel](text: str, origin: str, model: type[ModelT]) -> tuple[ModelT, str]:
    try:
        raw, body = split_front_matter(text, origin)
    except KBFormatError as exc:
        raise WikiFormatError(origin, str(exc).removeprefix(f"{origin}: ")) from exc
    try:
        return model.model_validate(raw), body
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise WikiFormatError(origin, f"{where}: {first['msg']}") from exc


def parse_notion(text: str, notion_id: str, origin: str) -> Notion:
    """Read a notion page.

    Args:
        text: The file.
        notion_id: Its identifier (`<domain>/<notion>`).
        origin: Its path, for error messages.

    Returns:
        The notion.

    Raises:
        WikiFormatError: If the front-matter or the `# ` title is missing or invalid.
    """
    meta, body = _meta(text, origin, NotionMeta)
    lines = body.strip("\n").split("\n")
    if not lines[0].startswith("# "):
        raise WikiFormatError(origin, "missing `# title` line after the front-matter")
    sections = [i for i, line in enumerate(lines) if line.startswith("## ")]
    end = sections[0] if sections else len(lines)
    return Notion(
        id=notion_id,
        meta=meta,
        title=lines[0][2:].strip(),
        summary="\n".join(lines[1:end]).strip(),
        headings=tuple(lines[i][3:].strip() for i in sections),
        body=body,
    )


def parse_domain(text: str, domain_id: str, origin: str) -> Domain:
    """Read a domain `index.md`.

    Args:
        text: The file.
        domain_id: The domain (its folder).
        origin: Its path, for error messages.

    Returns:
        The domain.

    Raises:
        WikiFormatError: If the front-matter is missing or invalid.
    """
    index, body = _meta(text, origin, DomainIndex)
    return Domain(id=domain_id, index=index, intro=body)


def load_wiki(files: Mapping[PurePosixPath, str], assets: Iterable[PurePosixPath]) -> Wiki:
    """Read every page of the wiki.

    Args:
        files: Markdown files, by path relative to `wiki/`. `<d>/index.md` is a domain,
            `<d>/<n>.md` a notion; anything else (`GUIDE.md`, deeper files) is ignored.
        assets: Figures and notebooks, relative to `wiki/`.

    Returns:
        The wiki; pages that cannot be read are listed in `unreadable`.
    """
    domains: dict[str, Domain] = {}
    notions: dict[str, Notion] = {}
    unreadable: dict[PurePosixPath, str] = {}
    for path, text in sorted(files.items()):
        if len(path.parts) != 2:  # noqa: PLR2004 - `<domain>/<page>.md`
            continue
        domain, name = path.parts[0], path.stem
        try:
            if path.name == INDEX:
                domains[domain] = parse_domain(text, domain, path.as_posix())
            else:
                notion_id = f"{domain}/{name}"
                notions[notion_id] = parse_notion(text, notion_id, path.as_posix())
        except WikiFormatError as exc:
            unreadable[path] = exc.reason
    return Wiki(domains=domains, notions=notions, assets=frozenset(assets), unreadable=unreadable)
