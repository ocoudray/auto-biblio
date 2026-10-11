"""Show the Markdown note written for a deep analysis, and how a re-write keeps your notes.

Run with `uv run python examples/note.py` (no network, no LLM).
"""

from datetime import date

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import (
    DeepAnalysis,
    Note,
    NoteMeta,
    ShortNote,
    merge_note,
    render_note,
)

META = NoteMeta(
    id=ItemId("arxiv:2410.12345"),
    kind="paper",
    title="Durable Agents: checkpointing long-running LLM agents",
    url="https://arxiv.org/abs/2410.12345",
    themes=(),
    links=("https://github.com/acme/durable-agents",),
    depth="short",
    source_text="abstract",
    first_seen=date(2026, 10, 7),
    analyzed_at=date(2026, 10, 11),
    model_id="google:gemini-3.5-flash",
    prompt_version="short_note_v1",
)


def main() -> None:
    """Write a short note, annotate it, then deepen it and print the result."""
    short = Note(
        meta=META,
        content=ShortNote(
            summary="Un harness qui checkpointe chaque appel d'outil d'un agent.",
            contribution="Reprise exacte après crash grâce à un journal d'événements.",
            relevance="Directement utile pour fiabiliser des agents en production.",
        ),
        my_notes="- À tester sur notre pipeline d'extraction.",
    )
    deep = Note(
        meta=META.model_copy(
            update={
                "depth": "deep",
                "source_text": "full_text",
                "prompt_version": "deep_analysis_v1",
            }
        ),
        content=DeepAnalysis(
            **short.content.model_dump(),
            problem="Les agents longs perdent leur état en cas de panne.",
            method=("Journal append-only des appels d'outils", "Rejeu au redémarrage"),
            results=("+12 % de tâches terminées sur un benchmark interne",),
            limitations=("Suppose des outils idempotents",),
            positioning="Généralise les checkpoints de LangGraph.",
            takeaways=("Rendre les outils idempotents avant tout",),
            further_reading=("https://github.com/acme/durable-agents",),
            verdict="À lire si vous faites tourner des agents plus de quelques minutes.",
            confidence="high",
        ),
    )
    print(render_note(merge_note(short, deep)))


if __name__ == "__main__":
    main()
