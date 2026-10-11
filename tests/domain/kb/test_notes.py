from datetime import date

import pytest

from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import (
    DeepAnalysis,
    Note,
    NoteMeta,
    ShortNote,
    merge_note,
    note_id_for,
    note_kind,
    note_path,
    note_slug,
    parse_note,
    render_note,
)

SHORT = ShortNote(
    summary="A harness  for\nagents.", contribution="Durable runs.", relevance="Agentic theme."
)
DEEP = DeepAnalysis(
    summary="A harness for agents.",
    contribution="Durable runs.",
    relevance="Agentic theme.",
    problem="Agents lose state.",
    method=("Checkpoint every step", "Replay from log"),
    results=("+12 % success on SWE-bench",),
    limitations=(),
    positioning="Extends LangGraph checkpoints.",
    takeaways=("Use event sourcing for agents",),
    further_reading=("https://example.com/paper",),
    verdict="Worth trying.",
    confidence="high",
)


def meta(**overrides: object) -> NoteMeta:
    base: dict[str, object] = {
        "id": "arxiv:2410.12345",
        "kind": "paper",
        "title": "Durable Agents",
        "url": "https://arxiv.org/abs/2410.12345",
        "themes": ["agentic"],
        "links": ["https://github.com/o/r"],
        "related": [],
        "depth": "short",
        "source_text": "abstract",
        "first_seen": date(2026, 10, 1),
        "analyzed_at": date(2026, 10, 11),
        "model_id": "google:gemini-3.5-flash",
        "prompt_version": "notes_v1",
    }
    return NoteMeta.model_validate(base | overrides)


@pytest.mark.parametrize(
    ("item_id", "slug"),
    [
        ("arxiv:2410.12345", "arxiv-2410.12345"),
        ("gh:Owner/Repo_x", "gh-owner-repo-x"),
        ("url:3f2a9c", "url-3f2a9c"),
    ],
)
def test_slug(item_id: str, slug: str) -> None:
    assert note_slug(ItemId(item_id)) == slug


def test_release_belongs_to_repo_note() -> None:
    assert note_id_for(ItemId("gh:o/r@v1.2")) == "gh:o/r"
    assert note_id_for(ItemId("arxiv:1")) == "arxiv:1"
    assert note_kind("release") == "tool"
    assert note_kind("discussion") == "post"
    assert str(note_path("tool", ItemId("gh:o/r"))) == "notes/tools/gh-o-r.md"


@pytest.mark.parametrize("content", [SHORT, DEEP])
def test_note_roundtrip(content: ShortNote) -> None:
    depth = "deep" if isinstance(content, DeepAnalysis) else "short"
    note = Note(meta=meta(depth=depth), content=content, my_notes="- my idea\n\nmore")
    text = render_note(note)
    assert parse_note(text, "x.md") == note
    assert render_note(parse_note(text, "x.md")) == text


def test_render_is_deterministic() -> None:
    text = render_note(Note(meta=meta(), content=SHORT))
    assert text.startswith("---\nid: arxiv:2410.12345\nkind: paper\n")
    assert "# Durable Agents\n\n## Résumé\n\nA harness for agents.\n" in text
    assert text.endswith("## Mes notes\n")
    assert SHORT.summary == "A harness for agents."  # whitespace normalized


def test_merge_keeps_my_notes_verbatim() -> None:
    mine = "**Read it twice.**\n\n- try on our corpus"
    existing = Note(meta=meta(), content=SHORT, my_notes=mine)
    new = Note(meta=meta(depth="deep", source_text="full_text"), content=DEEP)
    merged = merge_note(existing, new)
    assert merged.my_notes == mine
    assert merged.meta.depth == "deep"
    assert merge_note(None, new) == new


def test_merge_never_downgrades() -> None:
    existing = Note(meta=meta(depth="deep"), content=DEEP)
    new = Note(meta=meta(analyzed_at=date(2026, 10, 18)), content=SHORT)
    merged = merge_note(existing, new)
    assert merged.content == DEEP
    assert merged.meta.depth == "deep"


def test_merge_unions_links_and_keeps_first_seen() -> None:
    existing = Note(meta=meta(links=["https://a"], first_seen=date(2026, 9, 1)), content=SHORT)
    new = Note(meta=meta(links=["https://b"], themes=["rag"], related=["gh:o/r"]), content=SHORT)
    merged = merge_note(existing, new)
    assert merged.meta.links == ("https://a", "https://b")
    assert merged.meta.themes == (ThemeId("agentic"), ThemeId("rag"))
    assert merged.meta.related == ("gh:o/r",)
    assert merged.meta.first_seen == date(2026, 9, 1)


@pytest.mark.parametrize(
    "text",
    [
        "no front matter",
        "---\n- a list\n---\n# t\n",
        "---\nid: [unclosed\n---\n# t\n",
        "---\nid: x\n---\nno title\n",
        "---\nid: x\n---\n# t\n",
    ],
)
def test_parse_rejects_bad_files(text: str) -> None:
    with pytest.raises(KBFormatError, match=r"x\.md"):
        parse_note(text, "x.md")
