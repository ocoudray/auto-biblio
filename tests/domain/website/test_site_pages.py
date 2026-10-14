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
