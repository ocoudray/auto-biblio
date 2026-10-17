"""The catalogue of notions sent to the LLM, its signature and concept normalisation."""

import hashlib
import json
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.wiki.pages import Wiki

_SEPARATORS = re.compile(r"[\s_-]+")


class CatalogEntry(BaseModel):
    """What the LLM knows of a notion."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    aliases: tuple[str, ...]


def catalog(wiki: Wiki) -> tuple[CatalogEntry, ...]:
    """List the notions of the wiki.

    Args:
        wiki: The wiki.

    Returns:
        One entry per notion page, sorted by id.
    """
    return tuple(
        CatalogEntry(id=n.id, title=n.meta.title, aliases=n.meta.aliases)
        for n in sorted(wiki.notions.values(), key=lambda n: n.id)
    )


def signature(entries: Sequence[CatalogEntry]) -> str:
    """Fingerprint a catalogue: notes tagged with another one must be tagged again.

    Args:
        entries: The catalogue.

    Returns:
        The SHA-256 of the catalogue sorted by id, in hex.
    """
    payload = json.dumps(
        [e.model_dump() for e in sorted(entries, key=lambda e: e.id)], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def normalize(concept: str) -> str:
    """Reduce a concept name to a comparison key.

    Args:
        concept: Any name, title or alias.

    Returns:
        Lowercase, with dashes, underscores and runs of spaces turned into one space.
    """
    return _SEPARATORS.sub(" ", concept.lower()).strip()


def alias_index(entries: Sequence[CatalogEntry]) -> dict[str, str]:
    """Map every way of naming a notion to its id.

    Args:
        entries: The catalogue.

    Returns:
        Normalised id, title and aliases → notion id.
    """
    index: dict[str, str] = {}
    for entry in entries:
        for name in (entry.id, entry.title, *entry.aliases):
            index[normalize(name)] = entry.id
    return index
