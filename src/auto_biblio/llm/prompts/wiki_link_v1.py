"""Wiki link prompt, version 1: tag a batch of notes with the notions of the wiki."""

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.kb.notes import Note
from auto_biblio.domain.wiki.catalog import CatalogEntry, alias_index, normalize
from auto_biblio.domain.wiki.links import LinkResult
from auto_biblio.llm import LLMTask

VERSION = "wiki_link_v1"
MAX_MISSING = 3

_SYSTEM = """\
You link notes of an AI literature watch to the pages of a wiki of established notions.

Wiki notions (id, title, aliases):
{catalog}

For each note, return:
- notions: the ids of the notions the note uses or advances. Only ids from the list above.
  Cite a notion only when the note really relies on it, not for loose topical similarity.
- missing: at most 3 established, important concepts needed to understand the note that
  have no page above. Short canonical English names (e.g. "KV cache"). Empty if none.
Return one entry per note ref, every ref exactly once.
"""


class LinkInput(BaseModel):
    """One note as the LLM sees it."""

    model_config = ConfigDict(frozen=True)

    ref: str
    title: str
    summary: str
    contribution: str


class LinkVerdict(BaseModel):
    """What the LLM says of one note."""

    ref: str
    notions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


class LinkBatch(BaseModel):
    """The LLM output for a batch."""

    links: tuple[LinkVerdict, ...]


def to_inputs(notes: Sequence[Note]) -> tuple[LinkInput, ...]:
    """Turn notes into prompt inputs with short refs.

    Args:
        notes: The notes of a batch.

    Returns:
        One input per note, refs `n01`, `n02`…
    """
    return tuple(
        LinkInput(
            ref=f"n{index:02d}",
            title=note.meta.title,
            summary=note.content.summary,
            contribution=note.content.contribution,
        )
        for index, note in enumerate(notes, start=1)
    )


def wiki_link_task(
    batch: Sequence[LinkInput], entries: Sequence[CatalogEntry]
) -> LLMTask[LinkBatch]:
    """Build the LLM task of one batch.

    Args:
        batch: The notes of the batch.
        entries: The wiki catalogue.

    Returns:
        A task whose output must cover every ref of the batch.
    """
    refs = [i.ref for i in batch]
    catalog = json.dumps([e.model_dump() for e in entries], ensure_ascii=False, indent=1)
    payload = json.dumps([i.model_dump() for i in batch], ensure_ascii=False, indent=1)

    def check(output: LinkBatch, model_id: str) -> LinkBatch:
        answered = [v.ref for v in output.links]
        missing = [r for r in refs if r not in answered]
        if missing or len(answered) != len(set(answered)):
            msg = f"answer every note ref exactly once; missing: {', '.join(missing) or 'none'}"
            raise LLMOutputInvalidError(model_id, msg)
        return output

    return LLMTask(
        role="wiki_link",
        prompt_version=VERSION,
        system_prompt=_SYSTEM.format(catalog=catalog),
        user_prompt=f"Notes:\n{payload}",
        output_type=LinkBatch,
        validate=check,
    )


def to_results(
    batch: Sequence[LinkInput], output: LinkBatch, entries: Sequence[CatalogEntry]
) -> dict[str, LinkResult]:
    """Read the LLM output back against the catalogue.

    Args:
        batch: The notes of the batch.
        output: The validated output.
        entries: The wiki catalogue.

    Returns:
        By ref: notions named by id, title or alias, unknown ones dropped, and at most 3
        missing concepts.
    """
    aliases = alias_index(entries)
    refs = {i.ref for i in batch}
    results: dict[str, LinkResult] = {}
    for verdict in output.links:
        if verdict.ref not in refs:
            continue
        notions = {aliases[key] for n in verdict.notions if (key := normalize(n)) in aliases}
        results[verdict.ref] = LinkResult(
            notions=tuple(sorted(notions)), missing=verdict.missing[:MAX_MISSING]
        )
    return results
