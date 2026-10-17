from builders import make_note, make_theme_page

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.kb.notes import render_note
from auto_biblio.domain.kb.pages import render_theme_page
from auto_biblio.domain.website.pages import note_page, theme_page

LABELS = {ThemeId("agentic"): "Architectures agentiques"}


def test_note_page_inserts_metadata_under_the_title() -> None:
    note = make_note("arxiv:2610.1", depth="deep")
    page, parsed = note_page(render_note(note), "notes/papers/arxiv-2610.1.md", LABELS)
    lines = page.splitlines()
    title = lines.index("# Title arxiv:2610.1")
    assert lines[title + 1] == ""
    assert lines[title + 2] == (
        "> [Source](https://example.com/x) · Article · Architectures agentiques"
        " · fiche approfondie · vue le 2026-10-01 · analysée le 2026-10-11"
    )
    assert lines[title + 3] == ""
    assert parsed == note
    assert page.startswith("---\n")  # front-matter kept: zensical hides it


def test_note_page_short_note_without_theme() -> None:
    note = make_note("a:1", themes=())
    page, _ = note_page(render_note(note), "notes/papers/a-1.md", LABELS)
    assert "> [Source](https://example.com/x) · Article · fiche courte · vue le" in page


def test_unknown_theme_shows_its_id() -> None:
    note = make_note("a:1", themes=("retired",))
    page, _ = note_page(render_note(note), "notes/papers/a-1.md", LABELS)
    assert "· Article · retired · fiche courte" in page


def test_unreadable_note_is_kept_verbatim() -> None:
    assert note_page("# x\n", "notes/papers/x.md", LABELS) == ("# x\n", None)


def test_theme_page_shows_its_update_date() -> None:
    theme = make_theme_page()
    page, parsed = theme_page(render_theme_page(theme), "themes/agentic.md")
    lines = page.splitlines()
    assert lines[lines.index("# Agentic") + 2] == "> Mise à jour le 2026-10-13"
    assert parsed == theme


def test_unreadable_theme_page_is_kept_verbatim() -> None:
    assert theme_page("oops", "themes/x.md") == ("oops", None)


def test_note_body_cannot_inject_html() -> None:
    note = make_note("a:1")
    hostile = note.model_copy(
        update={
            "content": note.content.model_copy(update={"summary": "x <script>steal()</script>"})
        }
    )
    page, _ = note_page(render_note(hostile), "notes/papers/a-1.md", LABELS)
    assert "<script>" not in page
    assert "&lt;script>steal()&lt;/script>" in page


def test_theme_page_keeps_its_note_markers_but_not_raw_html() -> None:
    theme = make_theme_page()
    hostile = theme.model_copy(
        update={"content": theme.content.model_copy(update={"overview": "<iframe src=x>"})}
    )
    page, _ = theme_page(render_theme_page(hostile) + "<!-- note:a:1 -->\n", "themes/agentic.md")
    assert "<iframe" not in page
    assert "<!-- note:a:1 -->" in page


def test_note_page_lists_its_notions() -> None:
    page, _ = note_page(
        render_note(make_note("a:1")),
        "notes/papers/a-1.md",
        LABELS,
        notions=(("Attention", "../../wiki/llm/attention.md"),),
    )
    lines = page.splitlines()
    meta = next(i for i, line in enumerate(lines) if line.startswith("> [Source]"))
    assert lines[meta + 2] == "> Notions : [Attention](../../wiki/llm/attention.md)"
