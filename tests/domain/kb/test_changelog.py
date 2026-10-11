from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry, NoteChange, render_changelog
from auto_biblio.domain.kb.pages import RemovedLink


def test_changelog_render() -> None:
    entry = ChangelogEntry(
        week="2026-W41",
        notes=(
            NoteChange(
                note_id=ItemId("arxiv:1"),
                title="Durable  Agents",
                kind="paper",
                change="deepened",
                depth="deep",
                source_text="full_text",
            ),
        ),
        theme="agentic",  # pyright: ignore[reportArgumentType] - ThemeId at runtime
        links_added=("https://a",),
        links_removed=(RemovedLink(url="https://b", reason="Dead link."),),
        degradations=("extraction failed for url:x",),
    )
    text = render_changelog(entry)
    assert text.startswith("# Évolutions de la base — 2026-W41\n")
    assert "- Durable Agents (`arxiv:1`) : fiche approfondie, deep, lue depuis full_text" in text
    assert "Page `agentic` réécrite." in text
    assert "- https://b : Dead link." in text
    assert "## Dégradations" in text
    assert not entry.is_empty


def test_empty_changelog() -> None:
    entry = ChangelogEntry(week="2026-W41")
    text = render_changelog(entry)
    assert "Aucune fiche cette semaine." in text
    assert "Aucune page réécrite." in text
    assert "## Liens" not in text
    assert entry.is_empty
