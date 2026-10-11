"""Notes: one Markdown file per paper, tool or post of the knowledge base."""

import re
from datetime import date
from pathlib import PurePosixPath
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId, ItemKind
from auto_biblio.domain.kb.markdown import (
    clean,
    parse_list,
    render_document,
    render_list,
    render_text,
    split_document,
)

NoteKind = Literal["paper", "tool", "post"]
Depth = Literal["short", "deep"]
SourceText = Literal["abstract", "full_text", "snippet", "title"]
Confidence = Literal["low", "medium", "high"]

MY_NOTES = "Mes notes"
"""Heading of the section the pipeline never rewrites."""

_KIND_OF: dict[ItemKind, NoteKind] = {
    "paper": "paper",
    "repo": "tool",
    "release": "tool",
    "blog_post": "post",
    "discussion": "post",
}
_SLUG_UNSAFE = re.compile(r"[^a-z0-9.-]+")


def note_kind(kind: ItemKind) -> NoteKind:
    """Map an item kind to the kind of its note.

    Args:
        kind: The item kind.

    Returns:
        `paper`, `tool` (repositories and releases) or `post`.
    """
    return _KIND_OF[kind]


def note_id_for(item_id: ItemId) -> ItemId:
    """Return the note an item belongs to: a release belongs to its repository's note.

    Args:
        item_id: The item.

    Returns:
        The note id.
    """
    if item_id.startswith("gh:") and "@" in item_id:
        return ItemId(item_id.split("@", 1)[0])
    return item_id


def note_slug(note_id: ItemId) -> str:
    """Turn a note id into a file name.

    Args:
        note_id: The note id.

    Returns:
        Lowercase, with every run of characters outside `[a-z0-9.-]` replaced by `-`.
    """
    return _SLUG_UNSAFE.sub("-", note_id.lower()).strip("-")


def note_path(kind: NoteKind, note_id: ItemId) -> PurePosixPath:
    """Locate a note inside the knowledge base.

    Args:
        kind: The note kind.
        note_id: The note id.

    Returns:
        `notes/<kind>s/<slug>.md`.
    """
    return PurePosixPath("notes", f"{kind}s", f"{note_slug(note_id)}.md")


class _Content(BaseModel):
    model_config = ConfigDict(frozen=True)

    @field_validator("*", mode="after")
    @classmethod
    def _single_line(cls, value: object) -> object:
        # Values are rendered on one line; normalizing here makes Markdown round trips exact.
        if isinstance(value, str):
            return clean(value)
        if isinstance(value, tuple):
            items = cast("tuple[object, ...]", value)  # tuple fields of these models hold str
            return tuple(clean(v) if isinstance(v, str) else v for v in items)
        return value


class ShortNote(_Content):
    """What the LLM writes for a short note (from the abstract)."""

    summary: str
    contribution: str
    relevance: str


class DeepAnalysis(ShortNote):
    """What the LLM writes for a deep analysis (from the full text)."""

    problem: str
    method: tuple[str, ...]
    results: tuple[str, ...]
    limitations: tuple[str, ...]
    positioning: str
    takeaways: tuple[str, ...]
    further_reading: tuple[str, ...]
    verdict: str
    confidence: Confidence


_TEXT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("summary", "Résumé"),
    ("contribution", "Contribution"),
    ("relevance", "Pourquoi c'est utile"),
    ("problem", "Problème"),
)
_DEEP_SECTIONS: tuple[tuple[str, str, bool], ...] = (
    # (field, heading, is_list), after the text sections above
    ("method", "Méthode", True),
    ("results", "Résultats", True),
    ("limitations", "Limites", True),
    ("positioning", "Positionnement", False),
    ("takeaways", "En pratique", True),
    ("further_reading", "Pour aller plus loin", True),
    ("verdict", "Verdict", False),
    ("confidence", "Confiance", False),
)


class NoteMeta(BaseModel):
    """Front-matter of a note."""

    model_config = ConfigDict(frozen=True)

    id: ItemId
    kind: NoteKind
    title: str
    url: str
    themes: tuple[ThemeId, ...]
    links: tuple[str, ...] = ()
    related: tuple[ItemId, ...] = ()
    depth: Depth
    source_text: SourceText
    first_seen: date
    analyzed_at: date
    model_id: str
    prompt_version: str

    @field_validator("themes", "links", "related")
    @classmethod
    def _sorted_unique[T: str](cls, value: tuple[T, ...]) -> tuple[T, ...]:
        return tuple(sorted(set(value)))


class Note(BaseModel):
    """A note: metadata, the LLM's content and the reader's own notes."""

    model_config = ConfigDict(frozen=True)

    meta: NoteMeta
    content: ShortNote | DeepAnalysis
    my_notes: str = ""
    """Free Markdown under `## Mes notes`, kept verbatim."""

    @property
    def path(self) -> PurePosixPath:
        """Location of the note inside the knowledge base."""
        return note_path(self.meta.kind, self.meta.id)


def render_note(note: Note) -> str:
    """Render a note to Markdown.

    Args:
        note: The note.

    Returns:
        The file content.
    """
    content = note.content
    sections: list[tuple[str, str]] = [
        (heading, render_text(str(getattr(content, field))))
        for field, heading in _TEXT_SECTIONS
        if hasattr(content, field)
    ]
    if isinstance(content, DeepAnalysis):
        for field, heading, is_list in _DEEP_SECTIONS:
            value: object = getattr(content, field)
            body = render_list(_strings(value)) if is_list else render_text(str(value))
            sections.append((heading, body))
    sections.append((MY_NOTES, note.my_notes.strip("\n")))
    return render_document(note.meta.model_dump(mode="json"), note.meta.title, sections)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        return ()
    return tuple(str(v) for v in cast("tuple[object, ...]", value))


def parse_note(text: str, origin: str) -> Note:
    """Read back a note written by `render_note`.

    Args:
        text: The file content.
        origin: The file, for error messages.

    Returns:
        The note.

    Raises:
        KBFormatError: If the file cannot be read back.
    """
    meta_raw, _, sections = split_document(text, origin)
    try:
        meta = NoteMeta.model_validate(meta_raw)
        fields: dict[str, object] = {
            field: sections.get(heading, "") for field, heading in _TEXT_SECTIONS
        }
        if meta.depth == "deep":
            for field, heading, is_list in _DEEP_SECTIONS:
                body = sections.get(heading, "")
                fields[field] = parse_list(body) if is_list else clean(body)
            content: ShortNote | DeepAnalysis = DeepAnalysis.model_validate(fields)
        else:
            content = ShortNote.model_validate(fields)
    except ValidationError as exc:
        raise KBFormatError(origin, f"invalid note: {exc.errors()[0]['msg']}") from exc
    return Note(meta=meta, content=content, my_notes=sections.get(MY_NOTES, ""))


def merge_note(existing: Note | None, new: Note) -> Note:
    """Combine a freshly written note with the one already in the knowledge base.

    The reader's notes and the first sighting are kept, links, related notes and themes are
    united, and a deep note is never replaced by a short one.

    Args:
        existing: The note on disk, if any.
        new: The note just produced.

    Returns:
        The note to write.
    """
    if existing is None:
        return new
    downgrade = existing.meta.depth == "deep" and new.meta.depth == "short"
    base = existing if downgrade else new
    meta = base.meta.model_copy(
        update={
            "first_seen": min(existing.meta.first_seen, new.meta.first_seen),
            "links": tuple(sorted({*existing.meta.links, *new.meta.links})),
            "related": tuple(sorted({*existing.meta.related, *new.meta.related})),
            "themes": tuple(sorted({*existing.meta.themes, *new.meta.themes})),
        }
    )
    return Note(meta=meta, content=base.content, my_notes=existing.my_notes)
