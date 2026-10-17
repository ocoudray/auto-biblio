"""Links between notes and notions, and the concepts the wiki still lacks."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.wiki.catalog import CatalogEntry, alias_index, normalize


class NoteLinks(BaseModel):
    """The notions of one note, and the catalogue signature they were found with."""

    model_config = ConfigDict(frozen=True)

    notions: tuple[str, ...]
    signature: str


class Candidate(BaseModel):
    """A concept notes rely on that has no page yet."""

    model_config = ConfigDict(frozen=True)

    name: str
    """The name as first seen."""
    notes: tuple[ItemId, ...]
    first_seen: date
    last_seen: date

    @property
    def count(self) -> int:
        """Number of notes that need the concept."""
        return len(self.notes)


class WikiLinks(BaseModel):
    """Everything `wiki link` knows: per-note notions and candidate concepts."""

    model_config = ConfigDict(frozen=True)

    notes: dict[ItemId, NoteLinks] = {}
    candidates: dict[str, Candidate] = {}
    """By normalised name."""


class LinkResult(BaseModel):
    """What the LLM found for one note."""

    model_config = ConfigDict(frozen=True)

    notions: tuple[str, ...]
    missing: tuple[str, ...]


def stale_notes(note_ids: Iterable[ItemId], links: WikiLinks, sig: str) -> list[ItemId]:
    """Select the notes to tag: new ones, and those tagged with another catalogue.

    Args:
        note_ids: Every note of the knowledge base.
        links: What is known.
        sig: Signature of the current catalogue.

    Returns:
        The notes to tag, in the given order.
    """
    return [n for n in note_ids if (known := links.notes.get(n)) is None or known.signature != sig]


def merge_links(  # noqa: PLR0913 - keyword-only inputs of one merge
    links: WikiLinks,
    results: Mapping[ItemId, LinkResult],
    *,
    entries: Sequence[CatalogEntry],
    sig: str,
    existing: frozenset[ItemId],
    today: date,
) -> WikiLinks:
    """Merge this week's tagging into what is known.

    Args:
        links: What is known.
        results: New tagging, by note.
        entries: The current catalogue.
        sig: Its signature.
        existing: Notes still in the knowledge base; the others are forgotten.
        today: Date of the run.

    Returns:
        The links: a `missing` concept that names a notion becomes a link, and a candidate
        that now names a notion, or that no note needs any more, is dropped.
    """
    aliases = alias_index(entries)
    notes = {n: known for n, known in links.notes.items() if n in existing}
    candidates = {
        key: c.model_copy(
            update={"notes": tuple(n for n in c.notes if n in existing and n not in results)}
        )
        for key, c in links.candidates.items()
    }
    for note_id, result in sorted(results.items()):
        if note_id not in existing:
            continue
        found = set(result.notions)
        for concept in result.missing:
            key = normalize(concept)
            if key in aliases:
                found.add(aliases[key])
                continue
            current = candidates.get(key)
            if current is None:
                candidates[key] = Candidate(
                    name=concept, notes=(note_id,), first_seen=today, last_seen=today
                )
            elif note_id not in current.notes:
                candidates[key] = current.model_copy(
                    update={"notes": (*current.notes, note_id), "last_seen": today}
                )
            else:
                candidates[key] = current.model_copy(update={"last_seen": today})
        notes[note_id] = NoteLinks(notions=tuple(sorted(found)), signature=sig)
    kept = {k: c for k, c in candidates.items() if c.notes and k not in aliases}
    return WikiLinks(notes=notes, candidates=kept)
