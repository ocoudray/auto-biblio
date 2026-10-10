from datetime import UTC, date, datetime

from builders import make_features, make_run, make_verdict

from auto_biblio.domain.analysis import (
    AnalysisOutcome,
    AnalysisRun,
    note_themes,
    pick_theme,
    plan_notes,
)
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry
from auto_biblio.domain.kb.notes import Depth, NoteMeta
from auto_biblio.domain.triage import LLMUsage, ScoredItem

VERSIONS: dict[Depth, str] = {"short": "short_note_v1", "deep": "deep_analysis_v1"}
A, R, T = ThemeId("agentic"), ThemeId("rag"), ThemeId("tabular")


def scored(item_id: str, final: float, slot: str | None = "theme", **extra: object) -> ScoredItem:
    base: dict[str, object] = {
        "item_id": item_id,
        "features": make_features(item_id),
        "prescore": 0.5,
        "final_score": final,
        "slot": slot,
        "theme": "agentic",
    }
    return ScoredItem.model_validate(base | extra)


def meta(note_id: str, depth: Depth, version: str) -> NoteMeta:
    return NoteMeta.model_validate(
        {
            "id": note_id,
            "kind": "paper",
            "title": "t",
            "url": "https://x",
            "themes": ["agentic"],
            "depth": depth,
            "source_text": "abstract",
            "first_seen": date(2026, 10, 1),
            "analyzed_at": date(2026, 10, 1),
            "model_id": "m",
            "prompt_version": version,
        }
    )


def plans_of(
    items: tuple[ScoredItem, ...], existing: dict[ItemId, NoteMeta] | None = None, deep: int = 2
) -> list[tuple[str, str, str]]:
    plans = plan_notes(make_run("2026-W41", items), existing or {}, deep, VERSIONS)
    return [(p.item_id, p.depth, p.action) for p in plans]


def test_top_items_are_deep_and_discoveries_short() -> None:
    items = (
        scored("a:1", 0.9),
        scored("a:2", 0.8),
        scored("a:3", 0.7),
        scored("d:1", 0.95, slot="discovery"),
        scored("x:0", 0.1, slot=None),
    )
    assert plans_of(items) == [
        ("d:1", "short", "create"),
        ("a:1", "deep", "create"),
        ("a:2", "deep", "create"),
        ("a:3", "short", "create"),
    ]


def test_existing_notes() -> None:
    existing = {
        ItemId("a:1"): meta("a:1", "deep", "deep_analysis_v1"),
        ItemId("a:2"): meta("a:2", "short", "short_note_v1"),
        ItemId("a:3"): meta("a:3", "short", "short_note_v0"),
        ItemId("a:4"): meta("a:4", "short", "short_note_v1"),
    }
    items = (scored("a:1", 0.9), scored("a:2", 0.8), scored("a:3", 0.7), scored("a:4", 0.6))
    assert plans_of(items, existing) == [
        ("a:1", "deep", "skip"),
        ("a:2", "deep", "deepen"),
        ("a:3", "short", "refresh"),
        ("a:4", "short", "skip"),
    ]


def test_releases_map_to_repo_note() -> None:
    items = (scored("gh:o/r@v2", 0.9), scored("gh:o/r@v1", 0.8), scored("gh:o/r", 0.7))
    plans = plan_notes(make_run("w", items), {}, 1, VERSIONS)
    assert [(p.note_id, p.action) for p in plans] == [
        ("gh:o/r", "create"),
        ("gh:o/r", "skip"),
        ("gh:o/r", "skip"),
    ]


def test_note_themes() -> None:
    with_verdict = scored(
        "a:1", 0.9, verdict=make_verdict(scores={"rag": 4, "agentic": 2, "tabular": 3})
    )
    assert note_themes(with_verdict, 3) == (R, T)
    low = scored("a:1", 0.9, verdict=make_verdict(scores={"rag": 1}))
    assert note_themes(low, 3) == (A,)
    assert note_themes(scored("a:1", 0.9, theme=None), 3) == ()


def test_rotation_prefers_touched_oldest() -> None:
    updated = {A: date(2026, 9, 1), R: date(2026, 8, 1), T: date(2026, 7, 1)}
    assert pick_theme([A, R, T], updated, frozenset({A, R})) == R
    assert pick_theme([A, R, T], {A: date(2026, 9, 1)}, frozenset({A, R})) == R  # R has no page


def test_rotation_without_touched() -> None:
    updated = {A: date(2026, 9, 1), R: date(2026, 9, 1), T: date(2026, 10, 1)}
    assert pick_theme([A, R, T], updated, frozenset()) == A


def test_run_helpers() -> None:
    run = AnalysisRun(
        week="2026-W41",
        run_id="r",
        generated_at=datetime(2026, 10, 11, tzinfo=UTC),
        outcomes=(AnalysisOutcome(item_id=ItemId("a:1"), note_id=ItemId("a:1"), status="created"),),
        theme=None,
        changelog=ChangelogEntry(week="2026-W41"),
        usage=(
            LLMUsage(
                role="short_note",
                model_id="m",
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.0,
                cached=False,
            ),
        ),
    )
    assert run.usage_totals() == (0.0, 15)
    outcome = run.outcome_for(ItemId("a:1"))
    assert outcome is not None
    assert outcome.status == "created"
    assert run.outcome_for(ItemId("a:2")) is None
