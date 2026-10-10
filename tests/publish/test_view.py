from datetime import timedelta

from builders import NOW, make_features, make_item, make_run, make_verdict

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.run_report import RunReport, SourceReport, SourceStatus
from auto_biblio.domain.triage import ScoredItem, ScoringReport
from auto_biblio.publish.view import HealthSummary, build_view
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
