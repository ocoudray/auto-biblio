"""Theme page prompt, version 1: rewrite the state of the art of one theme from its notes."""

import json
from collections.abc import Sequence

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.kb.notes import DeepAnalysis, Note
from auto_biblio.domain.kb.pages import ThemePageContent, check_links_kept
from auto_biblio.llm import LLMTask
from auto_biblio.repo_config.profile import Theme

VERSION = "theme_page_v1"

_SYSTEM = """\
You maintain the page of one theme in a personal knowledge base on AI, read by an expert
practitioner. Write in French; keep technical terms and names in English. Each field is plain
text on a single line, without Markdown.

Theme: {label}
Scope: {description}

Rewrite the page from the previous page (if any) and the notes of the theme:
- overview: a dense paragraph on the current state of the art.
- key_concepts, dominant_approaches, open_questions: short items.
- reference_tools: tools, libraries or models worth knowing, with their URL, and the id of
  their note when one of the notes is about them (note_id), else null.
- further_reading: the most useful URLs, taken from the notes or the previous page.
Keep every link of the previous page. To drop one (dead, superseded, off-topic), list it in
removed_links with a one-sentence reason. Never invent a URL.
"""


def _note_digest(note: Note) -> dict[str, object]:
    content = note.content
    digest: dict[str, object] = {
        "id": note.meta.id,
        "title": note.meta.title,
        "url": note.meta.url,
        "summary": content.summary,
        "contribution": content.contribution,
        "links": list(note.meta.links),
    }
    if isinstance(content, DeepAnalysis):
        digest["verdict"] = content.verdict
        digest["takeaways"] = list(content.takeaways)
    return digest


def theme_page_task(
    theme: Theme, old: ThemePageContent | None, notes: Sequence[Note], max_chars: int
) -> LLMTask[ThemePageContent]:
    """Build the task of a theme page.

    Notes are sent most recent first, until `max_chars` is reached. The validation keeps
    every previous link and only accepts note ids that were sent.

    Args:
        theme: The theme.
        old: The current page, if any.
        notes: The notes of the theme.
        max_chars: Size cap of the notes sent.

    Returns:
        The task.
    """
    sent: list[dict[str, object]] = []
    size = 0
    for note in sorted(notes, key=lambda n: (n.meta.analyzed_at, n.meta.id), reverse=True):
        digest = _note_digest(note)
        size += len(json.dumps(digest, ensure_ascii=False))
        if sent and size > max_chars:
            break
        sent.append(digest)
    ids = {str(d["id"]) for d in sent}

    def check(output: ThemePageContent, model_id: str) -> ThemePageContent:
        unknown = sorted({str(t.note_id) for t in output.reference_tools if t.note_id} - ids)
        if unknown:
            msg = f"reference_tools.note_id must be one of the notes sent; unknown: {unknown}"
            raise LLMOutputInvalidError(model_id, msg)
        return check_links_kept(old, output, model_id)

    previous = old.model_dump(mode="json", exclude={"removed_links"}) if old else None
    payload = json.dumps({"previous_page": previous, "notes": sent}, ensure_ascii=False, indent=1)
    return LLMTask(
        role="synthesis",
        prompt_version=VERSION,
        system_prompt=_SYSTEM.format(
            label=theme.label, description=" ".join(theme.description.split())
        ),
        user_prompt=payload,
        output_type=ThemePageContent,
        validate=check,
    )
