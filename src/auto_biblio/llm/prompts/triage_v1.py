"""Triage prompt, version 1: rate a batch of items against the interest profile."""

import json
from collections.abc import Sequence

from auto_biblio.domain.features import ContextLevel, ThemeId
from auto_biblio.domain.models import Item
from auto_biblio.domain.triage import TriageBatch, TriageInput, validate_batch
from auto_biblio.llm import LLMTask
from auto_biblio.repo_config.profile import Theme

PROMPT_VERSION = "triage_v1"

_INSTRUCTIONS = """\
You triage new AI content (papers, repositories, releases, blog posts, discussions) for one
reader, according to the interest themes below.

For each item of the batch, answer with:
- ref: the item's ref, unchanged; answer for every item, and only for them.
- relevance: for each theme the item is about, an integer from 0 (unrelated) to 5 (core
  of the theme). Leave out the themes the item is not about. Use only the theme ids below.
- item_type: advance (new method or result), tool (library, product, model release),
  survey (state of the art, benchmark, comparison), opinion, or other.
- novelty: low, medium or high, for a reader who follows the field closely.
- confidence: low, medium or high, how sure you are of your rating.
- reason: one sentence of at most 30 words saying why it matters (or not) for the reader.

Rate the probable relevance. Some items only come with a title (context_level
title_only) or a short snippet: do not penalize them for the missing text; lower your
confidence instead.

Themes:
"""


def system_prompt(themes: Sequence[Theme]) -> str:
    """Build the system prompt for a profile.

    Args:
        themes: The themes of the profile.

    Returns:
        The instructions followed by one block per theme.
    """
    blocks = [
        f"- id: {t.id}\n  label: {t.label}\n  description: {' '.join(t.description.split())}"
        for t in themes
    ]
    return _INSTRUCTIONS + "\n".join(blocks)


def to_inputs(items: Sequence[tuple[Item, str | None, ContextLevel]]) -> tuple[TriageInput, ...]:
    """Turn items into what the LLM sees, with short sequential refs.

    Args:
        items: Each item with the text shown (summary or snippet) and its context level.

    Returns:
        One input per item, refs `i01`, `i02`...
    """
    return tuple(
        TriageInput(
            ref=f"i{index:02d}",
            title=item.title,
            text=text,
            source=item.sightings[0].source,
            kind=item.kind,
            context_level=level,
        )
        for index, (item, text, level) in enumerate(items, start=1)
    )


def make_batches(inputs: Sequence[TriageInput], size: int) -> list[tuple[TriageInput, ...]]:
    """Split inputs into batches.

    Args:
        inputs: Every input.
        size: Maximum batch size.

    Returns:
        Consecutive batches.
    """
    return [tuple(inputs[i : i + size]) for i in range(0, len(inputs), size)]


def triage_task(batch: Sequence[TriageInput], themes: Sequence[Theme]) -> LLMTask[TriageBatch]:
    """Build the LLM task of one batch.

    Args:
        batch: The inputs of the batch.
        themes: The themes of the profile.

    Returns:
        A task whose output is validated against the batch refs and the theme ids.
    """
    refs = frozenset(i.ref for i in batch)
    theme_ids = frozenset(ThemeId(t.id) for t in themes)
    payload = json.dumps([i.model_dump() for i in batch], ensure_ascii=False, indent=1)

    def check(output: TriageBatch, model_id: str) -> TriageBatch:
        return validate_batch(output, refs, theme_ids, model_id)

    return LLMTask(
        role="triage",
        prompt_version=PROMPT_VERSION,
        system_prompt=system_prompt(themes),
        user_prompt=f"Items to triage:\n{payload}",
        output_type=TriageBatch,
        validate=check,
    )
