from datetime import timedelta
from pathlib import PurePosixPath

from builders import NOW, make_features, make_item, make_note, make_run, make_verdict

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry, NoteChange
from auto_biblio.domain.kb.pages import RemovedLink
from auto_biblio.domain.run_report import RunReport, SourceReport, SourceStatus
from auto_biblio.domain.triage import ScoredItem, ScoringReport
from auto_biblio.publish.view import (
    HealthSummary,
    KBLinks,
    NoteLink,
    build_view,
    kb_changes,
    note_links,
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


def scored(item_id: str, theme: str | None, final: float, **extra: object) -> ScoredItem:
    base: dict[str, object] = {
        "item_id": item_id,
        "features": make_features(item_id),
        "prescore": 0.5,
        "verdict": make_verdict(scores={theme or "agentic": 4}, reason=f"Why {item_id}."),
        "final_score": final,
        "slot": "theme",
        "theme": theme,
    }
    return ScoredItem.model_validate(base | extra)


def view_of(items: tuple[ScoredItem, ...], repo: str | None = "me/data"):  # noqa: ANN201 - test helper
    run = make_run("2026-W41", items)
    by_id = {s.item_id: make_item(item_id=s.item_id, title=f"Title {s.item_id}") for s in items}
    return build_view(run, by_id, PROFILE, HealthSummary(), repo)


def test_view_groups_by_theme_in_score_order() -> None:
    view = view_of(
        (
            scored("a:1", "rag", 0.9),
            scored("a:2", "agentic", 0.5),
            scored("a:3", "agentic", 0.8),
            scored("a:4", None, 0.1, slot=None),
        )
    )
    assert [s.label for s in view.sections] == ["Agents", "RAG"]
    assert [i.title for i in view.sections[0].items] == ["Title a:3", "Title a:2"]
    assert view.count == 3


def test_badges_revenant_and_unverified() -> None:
    revenant = scored("a:1", "agentic", 0.9, features=make_features("a:1", revenant=True))
    unverified = scored("a:2", "agentic", 0.8, verdict=None)
    view = view_of((revenant, unverified))
    first, second = view.sections[0].items
    assert first.revenant
    assert not first.unverified
    assert second.unverified
    assert second.reason is None
    assert view.unverified == 1


def test_feedback_links_present() -> None:
    line = view_of((scored("arxiv:2410.1", "agentic", 0.9),)).sections[0].items[0]
    assert line.up_url is not None
    assert "issues/new" in line.up_url
    assert line.down_url is not None
    assert (
        view_of((scored("arxiv:2410.1", "agentic", 0.9),), repo=None).sections[0].items[0].up_url
        is None
    )


def test_discoveries_and_scoring_footer() -> None:
    discovery = scored("gh:o/x", "agentic", 0.1, slot="discovery")
    run = make_run("2026-W41", (discovery,)).model_copy(
        update={
            "scoring": ScoringReport(version="learned-x", auc_without_weak=0.7, auc_with_weak=0.8)
        }
    )
    view = build_view(
        run, {ItemId("gh:o/x"): make_item(item_id="gh:o/x")}, PROFILE, HealthSummary(), None
    )
    assert len(view.discoveries) == 1
    assert view.sections == ()
    assert view.auc == 0.8
    assert view.scoring_version == "learned-x"


def report(day: int, status: SourceStatus) -> RunReport:
    started = NOW - timedelta(days=day)
    return RunReport(
        run_id=f"r{day}",
        command="collect",
        started_at=started,
        finished_at=started,
        sources=(
            SourceReport(source="import-ai", status=status),
            SourceReport(source="hn", status="ok"),
            SourceReport(source="off", status="skipped"),
        ),
    )


def test_health_counts_consecutive_failures() -> None:
    health = HealthSummary.from_runs(
        [report(4, "ok"), report(3, "failed"), report(2, "failed"), report(1, "failed")]
    )
    assert [(s.source, s.consecutive_failures) for s in health.failing_sources] == [
        ("import-ai", 3)
    ]
    assert HealthSummary.from_runs([report(2, "failed"), report(1, "ok")]).failing_sources == ()


def test_note_links_and_verdict() -> None:
    run = make_run("2026-W41", (scored("a:1", "agentic", 0.9),))
    links = {
        ItemId("a:1"): NoteLink(
            url="https://github.com/me/data/blob/main/kb/notes/papers/a-1.md", verdict="À lire."
        )
    }
    view = build_view(
        run, {ItemId("a:1"): make_item(item_id="a:1")}, PROFILE, HealthSummary(), None, notes=links
    )
    line = view.sections[0].items[0]
    assert line.note_url is not None
    assert line.note_url.endswith("kb/notes/papers/a-1.md")
    assert line.verdict == "À lire."
    assert view.kb_changes.is_empty


def test_kb_changes_section() -> None:
    entry = ChangelogEntry(
        week="2026-W41",
        notes=(
            NoteChange(
                note_id=ItemId("a:1"),
                title="T",
                kind="paper",
                change="deepened",
                depth="deep",
                source_text="full_text",
            ),
            NoteChange(
                note_id=ItemId("a:2"),
                title="U",
                kind="paper",
                change="created",
                depth="short",
                source_text="abstract",
            ),
        ),
        theme=ThemeId("agentic"),
        links_removed=(RemovedLink(url="https://old", reason="Dead."),),
    )
    changes = kb_changes(
        entry,
        {ItemId("a:1"): PurePosixPath("notes/papers/a-1.md")},
        PROFILE,
        KBLinks(repo="me/data"),
    )
    assert [(c.title, c.change, c.url) for c in changes.notes] == [
        ("T", "fiche approfondie", "https://github.com/me/data/blob/main/kb/notes/papers/a-1.md"),
        ("U", "nouvelle fiche", None),
    ]
    assert changes.theme == "Agents"
    assert changes.theme_url == "https://github.com/me/data/blob/main/kb/themes/agentic.md"
    assert changes.links_removed == ("https://old : Dead.",)
    assert not changes.is_empty
    assert kb_changes(ChangelogEntry(week="w"), {}, PROFILE, KBLinks()).theme_url is None


def test_kb_links_point_to_the_site() -> None:
    links = KBLinks(repo="o/d", site_url="https://v.pages.dev/")
    assert links.page(PurePosixPath("notes/papers/x.md")) == "https://v.pages.dev/notes/papers/x/"
    assert links.digest("2026-W42") == "https://v.pages.dev/digests/2026-W42/"


def test_kb_links_fall_back_to_github() -> None:
    links = KBLinks(repo="o/d")
    assert (
        links.page(PurePosixPath("themes/a.md"))
        == "https://github.com/o/d/blob/main/kb/themes/a.md"
    )
    assert links.digest("2026-W42") is None
    assert KBLinks().page(PurePosixPath("themes/a.md")) is None


def test_kb_links_relative_markdown() -> None:
    links = KBLinks(relative_to="../", site_url="https://v.pages.dev/")
    assert links.page(PurePosixPath("notes/tools/y.md")) == "../notes/tools/y.md"


def test_note_links_use_the_links() -> None:
    run = make_run("2026-W41", (scored("a:1", "agentic", 0.9),))
    note = make_note("a:1", depth="deep")
    links = note_links(run, {note.meta.id: note}, KBLinks(site_url="https://v.pages.dev/"))
    assert links[ItemId("a:1")].url.startswith("https://v.pages.dev/notes/papers/")
    assert links[ItemId("a:1")].verdict is not None
    assert note_links(run, {}, KBLinks(site_url="https://v.pages.dev/")) == {}


def test_view_carries_the_online_url() -> None:
    run = make_run("2026-W41", (scored("a:1", "agentic", 0.9),))
    items = {ItemId("a:1"): make_item(item_id="a:1")}
    view = build_view(run, items, PROFILE, HealthSummary(), None, online_url="https://v/x/")
    assert view.online_url == "https://v/x/"
    assert build_view(run, items, PROFILE, HealthSummary(), None).online_url is None
