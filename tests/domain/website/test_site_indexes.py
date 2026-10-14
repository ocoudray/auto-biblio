from datetime import date

from builders import make_note, make_theme_page

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.kb.notes import Note
from auto_biblio.domain.website.indexes import (
    home,
    notes_by_theme,
    notes_index,
    weeks_index,
)
from auto_biblio.repo_config.profile import Profile

PROFILE = Profile.model_validate(
    {
        "themes": [
            {"id": "agentic", "label": "Agents", "description": "a"},
            {"id": "rag", "label": "RAG", "description": "r"},
        ]
    }
)
LABELS = {ThemeId("agentic"): "Agents", ThemeId("rag"): "RAG"}


def note(note_id: str, title: str, seen: date, *, kind: str = "paper", **extra: object) -> Note:
    base = make_note(note_id, **extra)  # pyright: ignore[reportArgumentType] - test helper
    meta = base.meta.model_copy(update={"title": title, "first_seen": seen, "kind": kind})
    return base.model_copy(update={"meta": meta})


def test_notes_index_is_a_table_newest_first() -> None:
    page = notes_index(
        "paper",
        (note("a:1", "Old", date(2026, 9, 1)), note("a:2", "New", date(2026, 10, 1))),
        LABELS,
    )
    lines = page.splitlines()
    assert lines[0] == "# Articles"
    assert "| Fiche | Thèmes | Profondeur | Vue le |" in lines
    rows = [line for line in lines if line.startswith("| [")]
    assert rows == [
        "| [New](papers/a-2.md) | Agents | fiche courte | 2026-10-01 |",
        "| [Old](papers/a-1.md) | Agents | fiche courte | 2026-09-01 |",
    ]


def test_notes_index_keeps_only_its_kind() -> None:
    page = notes_index("tool", (note("a:1", "Paper", date(2026, 9, 1)),), LABELS)
    assert page == "# Outils\n\nAucune fiche pour l'instant.\n"


def test_titles_with_pipes_and_brackets_stay_valid() -> None:
    page = notes_index("paper", (note("a:1", "A | B [v2]", date(2026, 9, 1)),), LABELS)
    assert "| [A \\| B (v2)](papers/a-1.md) |" in page


def test_notes_by_theme_profile_order_then_unknown_themes() -> None:
    page = notes_by_theme(
        (
            note("a:1", "One", date(2026, 9, 1), themes=("rag",)),
            note("a:2", "Two", date(2026, 9, 2), themes=("retired", "agentic")),
        ),
        PROFILE,
    )
    headings = [line for line in page.splitlines() if line.startswith("## ")]
    assert headings == ["## Agents", "## RAG", "## retired"]
    assert "- [Two](papers/a-2.md)" in page


def test_notes_by_theme_empty_theme() -> None:
    page = notes_by_theme((), PROFILE)
    assert page.count("Aucune fiche pour l'instant.") == 2


def test_home_with_theme_page_and_week() -> None:
    page = home(
        "Veille IA",
        PROFILE,
        {ThemeId("agentic"): make_theme_page()},
        latest_digest="2026-W42",
        latest_changelog="2026-W42",
    )
    assert page.startswith("# Veille IA\n")
    assert "- [Agents](themes/agentic.md) — mis à jour le 2026-10-13" in page
    assert "## Thèmes sans page pour l'instant\n\n- RAG" in page
    assert "- [Digest de la semaine 2026-W42](digests/2026-W42.md)" in page
    assert "- [Journal de la base 2026-W42](changelog/2026-W42.md)" in page


def test_home_of_an_empty_base() -> None:
    page = home("Veille IA", PROFILE, {}, latest_digest=None, latest_changelog=None)
    assert "Cette semaine" not in page
    assert "Aucune page thème pour l'instant." in page


def test_weeks_index_newest_first() -> None:
    page = weeks_index("Digests", ("2026-W41", "2026-W42"))
    assert page == "# Digests\n\n- [2026-W42](2026-W42.md)\n- [2026-W41](2026-W41.md)\n"
    assert weeks_index("Journal", ()) == "# Journal\n\nRien pour l'instant.\n"


def test_titles_cannot_inject_html() -> None:
    page = notes_index(
        "paper", (note("a:1", "<img src=x onerror=alert(1)>", date(2026, 9, 1)),), LABELS
    )
    assert "<img" not in page
    assert "&lt;img src=x onerror=alert(1)>" in page


def test_home_theme_labels_are_safe_link_texts() -> None:
    profile = Profile.model_validate(
        {"themes": [{"id": "agentic", "label": "Agents [beta]", "description": "a"}]}
    )
    page = home(
        "V",
        profile,
        {ThemeId("agentic"): make_theme_page()},
        latest_digest=None,
        latest_changelog=None,
    )
    assert "- [Agents (beta)](themes/agentic.md)" in page
