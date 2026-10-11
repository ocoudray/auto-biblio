"""Note prompts, version 1: a short note from the abstract, a deep analysis from the full text."""

import json
from collections.abc import Sequence

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.kb.notes import DeepAnalysis, ShortNote
from auto_biblio.domain.models import Item
from auto_biblio.extract import ExtractedText
from auto_biblio.llm import LLMTask
from auto_biblio.repo_config.profile import Theme

SHORT_VERSION = "short_note_v1"
DEEP_VERSION = "deep_analysis_v1"

_COMMON = """\
You write notes for a personal knowledge base on AI, read by an expert practitioner.
Write in French; keep technical terms, model, library and method names in English.
Be factual and dense: no hype, no filler. Never invent numbers, names or links: use only
what the provided text says. Each field is plain text on a single line, without Markdown.

The reader's interest themes:
{themes}
"""

_SHORT = """
Write a short note:
- summary: 2 to 3 sentences on what the content is and does.
- contribution: 1 sentence on what is new.
- relevance: 1 to 2 sentences on why it matters (or not) for the reader's themes.
"""

_DEEP = """
Write a deep analysis from the full text:
- summary, contribution, relevance: as for a short note.
- problem: the problem addressed.
- method: the key steps of the method, one item each.
- results: the main results, with the numbers the text gives (none if it gives none).
- limitations: limits stated by the authors or evident from the text.
- positioning: how it relates to prior work or alternatives the text mentions.
- takeaways: what a practitioner can apply, one item each.
- further_reading: URLs worth opening, copied exactly from the text; none if none.
- verdict: one sentence, is it worth the reader's time and why.
- confidence: low, medium or high, how complete the text was for this analysis.
"""


def _themes(themes: Sequence[Theme]) -> str:
    return "\n".join(f"- {t.label}: {' '.join(t.description.split())}" for t in themes)


def _payload(item: Item, extracted: ExtractedText) -> str:
    data = {
        "title": item.title,
        "url": str(item.url),
        "kind": item.kind,
        "text_source": extracted.source,
        "text": extracted.text,
    }
    return json.dumps(data, ensure_ascii=False, indent=1)


def short_note_task(
    item: Item, extracted: ExtractedText, themes: Sequence[Theme]
) -> LLMTask[ShortNote]:
    """Build the task of a short note.

    Args:
        item: The item.
        extracted: The text the note is written from (usually the abstract).
        themes: The reader's themes.

    Returns:
        The task.
    """
    return LLMTask(
        role="short_note",
        prompt_version=SHORT_VERSION,
        system_prompt=_COMMON.format(themes=_themes(themes)) + _SHORT,
        user_prompt=f"Content:\n{_payload(item, extracted)}",
        output_type=ShortNote,
    )


def deep_analysis_task(
    item: Item, extracted: ExtractedText, themes: Sequence[Theme]
) -> LLMTask[DeepAnalysis]:
    """Build the task of a deep analysis.

    Its validation rejects any `further_reading` URL that is not in the provided text.

    Args:
        item: The item.
        extracted: The full text.
        themes: The reader's themes.

    Returns:
        The task.
    """
    known = set(extracted.links) | {str(item.url)}

    def check(output: DeepAnalysis, model_id: str) -> DeepAnalysis:
        invented = [u for u in output.further_reading if u not in known and u not in extracted.text]
        if invented:
            msg = f"further_reading must only contain URLs from the text; not found: {invented}"
            raise LLMOutputInvalidError(model_id, msg)
        return output

    return LLMTask(
        role="deep_analysis",
        prompt_version=DEEP_VERSION,
        system_prompt=_COMMON.format(themes=_themes(themes)) + _DEEP,
        user_prompt=f"Content:\n{_payload(item, extracted)}",
        output_type=DeepAnalysis,
        validate=check,
    )
