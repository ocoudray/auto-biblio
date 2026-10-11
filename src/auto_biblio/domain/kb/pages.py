"""Theme pages: the state of the art of one theme, rewritten in rotation."""

import re
from datetime import date
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from auto_biblio.domain.errors import KBFormatError, LLMOutputInvalidError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.markdown import (
    clean,
    parse_list,
    render_document,
    render_list,
    render_text,
    split_document,
)

_TOOL_LINE = re.compile(
    r"^\[(?P<name>[^\]]+)\]\((?P<url>[^)\s]+)\)(?: <!-- note:(?P<note>\S+) -->)?$"
)


class ToolRef(BaseModel):
    """A reference tool of a theme."""

    model_config = ConfigDict(frozen=True)

    name: str
    url: str
    note_id: ItemId | None = None

    @field_validator("name")
    @classmethod
    def _plain_name(cls, value: str) -> str:
        # Square brackets would break the Markdown link the name is rendered into.
        return clean(value.replace("[", "(").replace("]", ")"))


class RemovedLink(BaseModel):
    """A link dropped from a theme page, with the reason."""

    model_config = ConfigDict(frozen=True)

    url: str
    reason: str


class ThemePageContent(BaseModel):
    """What the LLM writes for a theme page."""

    model_config = ConfigDict(frozen=True)

    overview: str
    key_concepts: tuple[str, ...]
    dominant_approaches: tuple[str, ...]
    reference_tools: tuple[ToolRef, ...]
    open_questions: tuple[str, ...]
    further_reading: tuple[str, ...]
    removed_links: tuple[RemovedLink, ...] = ()
    """Links of the previous page deliberately dropped; not rendered on the page."""

    @field_validator("overview")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return clean(value)

    @field_validator("key_concepts", "dominant_approaches", "open_questions", "further_reading")
    @classmethod
    def _clean_items(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(clean(v) for v in value)


class ThemePageMeta(BaseModel):
    """Front-matter of a theme page."""

    model_config = ConfigDict(frozen=True)

    theme: ThemeId
    label: str
    updated_at: date
    prompt_version: str
    model_id: str
    notes: tuple[ItemId, ...] = ()

    @field_validator("notes")
    @classmethod
    def _sorted(cls, value: tuple[ItemId, ...]) -> tuple[ItemId, ...]:
        return tuple(sorted(set(value)))


class ThemePage(BaseModel):
    """A theme page."""

    model_config = ConfigDict(frozen=True)

    meta: ThemePageMeta
    content: ThemePageContent

    @property
    def path(self) -> PurePosixPath:
        """Location of the page inside the knowledge base."""
        return PurePosixPath("themes", f"{self.meta.theme}.md")


_LIST_SECTIONS = (
    ("key_concepts", "Concepts clés"),
    ("dominant_approaches", "Approches dominantes"),
)
_TAIL_SECTIONS = (
    ("open_questions", "Questions ouvertes"),
    ("further_reading", "Pour aller plus loin"),
)


def page_links(content: ThemePageContent) -> frozenset[str]:
    """Collect the links of a page.

    Args:
        content: The page content.

    Returns:
        Reference tool URLs and further reading.
    """
    return frozenset({t.url for t in content.reference_tools} | set(content.further_reading))


def check_links_kept(
    old: ThemePageContent | None, new: ThemePageContent, model_id: str
) -> ThemePageContent:
    """Reject a rewrite that drops a link without saying why.

    Args:
        old: The current page content, if any.
        new: The rewrite.
        model_id: The model that wrote it, for the error.

    Returns:
        The rewrite, unchanged.

    Raises:
        LLMOutputInvalidError: Listing the links lost without a `removed_links` entry.
    """
    if old is None:
        return new
    justified = {r.url for r in new.removed_links if clean(r.reason)}
    lost = sorted(page_links(old) - page_links(new) - justified)
    if lost:
        msg = (
            "every link of the previous page must be kept, or listed in removed_links with "
            f"a reason; missing: {', '.join(lost)}"
        )
        raise LLMOutputInvalidError(model_id, msg)
    return new


def _note_link(note_id: ItemId, kind_paths: dict[ItemId, PurePosixPath]) -> str:
    path = kind_paths.get(note_id)
    target = f" · [fiche](../{path})" if path is not None else ""
    return f"{target} <!-- note:{note_id} -->"


def render_theme_page(
    page: ThemePage, note_paths: dict[ItemId, PurePosixPath] | None = None
) -> str:
    """Render a theme page to Markdown.

    Args:
        page: The page.
        note_paths: Location of each known note, to link reference tools to their note.

    Returns:
        The file content.
    """
    content = page.content
    paths = note_paths or {}
    tools = [
        f"[{t.name}]({t.url})" + (_note_link(t.note_id, paths) if t.note_id else "")
        for t in content.reference_tools
    ]
    sections = [
        ("Vue d'ensemble", render_text(content.overview)),
        *((heading, render_list(getattr(content, field))) for field, heading in _LIST_SECTIONS),
        ("Outils de référence", render_list(tools)),
        *((heading, render_list(getattr(content, field))) for field, heading in _TAIL_SECTIONS),
    ]
    return render_document(page.meta.model_dump(mode="json"), page.meta.label, sections)


def _parse_tool(line: str, origin: str) -> ToolRef:
    plain = re.sub(r" · \[fiche\]\([^)]*\)", "", line)
    match = _TOOL_LINE.match(plain)
    if match is None:
        raise KBFormatError(origin, f"unreadable reference tool line: {line!r}")
    note = match.group("note")
    return ToolRef(
        name=match.group("name"),
        url=match.group("url"),
        note_id=ItemId(note) if note else None,
    )


def parse_theme_page(text: str, origin: str) -> ThemePage:
    """Read back a theme page written by `render_theme_page`.

    Args:
        text: The file content.
        origin: The file, for error messages.

    Returns:
        The page.

    Raises:
        KBFormatError: If the file cannot be read back.
    """
    meta_raw, _, sections = split_document(text, origin)
    tools = tuple(
        _parse_tool(line, origin) for line in parse_list(sections.get("Outils de référence", ""))
    )
    fields: dict[str, object] = {
        "overview": sections.get("Vue d'ensemble", ""),
        "reference_tools": tools,
    }
    for field, heading in (*_LIST_SECTIONS, *_TAIL_SECTIONS):
        fields[field] = parse_list(sections.get(heading, ""))
    try:
        return ThemePage(
            meta=ThemePageMeta.model_validate(meta_raw),
            content=ThemePageContent.model_validate(fields),
        )
    except ValidationError as exc:
        raise KBFormatError(origin, f"invalid theme page: {exc.errors()[0]['msg']}") from exc
