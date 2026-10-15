from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath

import pytest
from builders import make_note

from auto_biblio.domain.analysis import AnalysisRun
from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry
from auto_biblio.domain.kb.pages import ThemePage, ThemePageContent, ThemePageMeta, ToolRef
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.kb import KBStore


def test_note_roundtrip_and_queries(tmp_path: Path) -> None:
    store = KBStore.open(tmp_path)
    assert store.get(ItemId("arxiv:1")) is None
    path = store.write_note(make_note("arxiv:1", my_notes="mine"))
    store.write_note(make_note("arxiv:2", themes=("rag",)))
    assert path == tmp_path / "notes" / "papers" / "arxiv-1.md"
    reopened = KBStore.open(tmp_path)
    note = reopened.get(ItemId("arxiv:1"))
    assert note is not None
    assert note.my_notes == "mine"
    assert [n.meta.id for n in reopened.all_notes()] == ["arxiv:1", "arxiv:2"]
    assert [n.meta.id for n in reopened.notes_for_theme(ThemeId("rag"))] == ["arxiv:2"]
    assert str(reopened.note_paths()[ItemId("arxiv:2")]) == "notes/papers/arxiv-2.md"


def test_rewrite_is_idempotent(tmp_path: Path) -> None:
    store = KBStore.open(tmp_path)
    path = store.write_note(make_note("arxiv:1"))
    before = path.read_bytes()
    store.write_note(make_note("arxiv:1"))
    assert path.read_bytes() == before


def test_broken_note_left_untouched(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    broken = tmp_path / "notes" / "papers" / "arxiv-1.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("hand written, no front matter")
    store = KBStore.open(tmp_path)
    assert "skipping unreadable note" in caplog.text
    with pytest.raises(KBFormatError, match="left untouched"):
        store.write_note(make_note("arxiv:1"))
    assert broken.read_text() == "hand written, no front matter"


def test_theme_page_and_changelog(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = KBStore.open(tmp_path)
    store.write_note(make_note("gh:o/r"))
    theme = ThemeId("agentic")
    assert store.read_theme(theme) is None
    page = ThemePage(
        meta=ThemePageMeta(
            theme=theme,
            label="Agents",
            updated_at=date(2026, 10, 11),
            prompt_version="v",
            model_id="m",
        ),
        content=ThemePageContent(
            overview="o",
            key_concepts=(),
            dominant_approaches=(),
            reference_tools=(
                ToolRef(name="R", url="https://github.com/o/r", note_id=ItemId("gh:o/r")),
            ),
            open_questions=(),
            further_reading=(),
        ),
    )
    path = store.write_theme(page)
    assert "[fiche](../notes/papers/gh-o-r.md)" in path.read_text()
    assert store.read_theme(theme) == page
    path.write_text("garbage")
    assert store.read_theme(theme) is None
    assert "unreadable theme page" in caplog.text
    log = store.write_changelog(ChangelogEntry(week="2026-W41"))
    assert log == tmp_path / "changelog" / "2026-W41.md"


def test_analysis_store(tmp_path: Path) -> None:
    store = AnalysisStore(tmp_path)
    assert store.read("2026-W41") is None
    run = AnalysisRun(
        week="2026-W41",
        run_id="r",
        generated_at=datetime(2026, 10, 11, tzinfo=UTC),
        outcomes=(),
        theme=None,
        changelog=ChangelogEntry(week="2026-W41"),
    )
    assert store.write(run) == tmp_path / "analysis" / "2026-W41.json"
    assert store.read("2026-W41") == run


def test_files_returns_every_page_source(tmp_path: Path) -> None:
    store = KBStore.open(tmp_path)
    store.write_note(make_note("arxiv:1"))
    (tmp_path / "themes").mkdir()
    (tmp_path / "themes" / "agentic.md").write_text("theme")
    store.write_changelog(ChangelogEntry(week="2026-W42"))
    (tmp_path / ".gitkeep").write_text("")
    files = store.files()
    assert sorted(str(p) for p in files) == [
        "changelog/2026-W42.md",
        "notes/papers/arxiv-1.md",
        "themes/agentic.md",
    ]
    assert files[PurePosixPath("themes/agentic.md")] == "theme"
