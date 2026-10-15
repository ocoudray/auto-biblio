from pathlib import PurePosixPath

from builders import make_note, make_theme_page

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import render_note
from auto_biblio.domain.kb.pages import render_theme_page
from auto_biblio.domain.website.plan import NavEntry, SiteInputs, plan_site
from auto_biblio.repo_config.profile import Profile

PROFILE = Profile.model_validate(
    {
        "themes": [
            {"id": "agentic", "label": "Agents", "description": "a"},
            {"id": "rag", "label": "RAG", "description": "r"},
        ]
    }
)
P = PurePosixPath


def inputs(**extra: object) -> SiteInputs:
    note = make_note("a:1")
    theme = make_theme_page(notes=("a:1",))
    paths = {ItemId("a:1"): note.path}
    base: dict[str, object] = {
        "title": "Veille IA",
        "profile": PROFILE,
        "kb_files": {
            note.path: render_note(note),
            P("themes/agentic.md"): render_theme_page(theme, paths),
            P("changelog/2026-W42.md"): "# Évolutions de la base — 2026-W42\n",
        },
        "digests": {"2026-W42": "# Digest — 2026-W42\n"},
    }
    return SiteInputs.model_validate(base | extra)


def test_plan_has_every_page() -> None:
    plan = plan_site(inputs())
    assert set(plan.pages) == {
        P("index.md"),
        P("notes/papers/a-1.md"),
        P("themes/agentic.md"),
        P("changelog/2026-W42.md"),
        P("changelog/index.md"),
        P("digests/2026-W42.md"),
        P("digests/index.md"),
        P("notes/papers.md"),
        P("notes/tools.md"),
        P("notes/posts.md"),
        P("notes/by-theme.md"),
    }
    assert "> [Source](https://example.com/x)" in plan.pages[P("notes/papers/a-1.md")]
    assert "> Mise à jour le 2026-10-13" in plan.pages[P("themes/agentic.md")]
    assert plan.pages[P("digests/2026-W42.md")] == "# Digest — 2026-W42\n"
    assert "(digests/2026-W42.md)" in plan.pages[P("index.md")]
    assert plan.warnings == ()


def test_navigation() -> None:
    assert plan_site(inputs()).nav == (
        NavEntry(title="Accueil", path="index.md"),
        NavEntry(title="Thèmes", children=(NavEntry(title="Agents", path="themes/agentic.md"),)),
        NavEntry(
            title="Fiches",
            children=(
                NavEntry(title="Articles", path="notes/papers.md"),
                NavEntry(title="Outils", path="notes/tools.md"),
                NavEntry(title="Billets", path="notes/posts.md"),
                NavEntry(title="Par thème", path="notes/by-theme.md"),
            ),
        ),
        NavEntry(title="Journal", path="changelog/index.md"),
        NavEntry(title="Digests", path="digests/index.md"),
    )


def test_unreadable_note_is_published_with_a_warning() -> None:
    plan = plan_site(inputs(kb_files={P("notes/papers/x.md"): "# broken\n"}))
    assert plan.pages[P("notes/papers/x.md")] == "# broken\n"
    assert plan.warnings == ("unreadable notes/papers/x.md",)
    assert "x.md" not in plan.pages[P("notes/papers.md")]


def test_unreadable_theme_page_is_published_with_a_warning() -> None:
    plan = plan_site(inputs(kb_files={P("themes/agentic.md"): "oops"}))
    assert plan.pages[P("themes/agentic.md")] == "oops"
    assert plan.warnings == ("unreadable themes/agentic.md",)


def test_empty_base() -> None:
    plan = plan_site(inputs(kb_files={}, digests={}))
    assert len(plan.pages) == 7
    assert [entry.title for entry in plan.nav] == ["Accueil", "Fiches", "Journal", "Digests"]
