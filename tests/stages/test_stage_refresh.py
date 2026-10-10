from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from builders import NOW, make_features, make_item, make_run

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Sighting
from auto_biblio.domain.triage import ScoredItem
from auto_biblio.repo_config.triage import RefreshConfig
from auto_biblio.stages.refresh import SignalRefreshStage
from auto_biblio.store.items import ItemStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.signals import SignalStore
from auto_biblio.store.triage import TriageStore


class Stars:
    source = "refresh:gh_stars"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.asked: list[str] = []

    def stars(self, repos: Sequence[str]) -> dict[str, int]:
        self.asked.extend(repos)
        if self.fail:
            raise SourceUnavailableError(self.source, "down")
        return dict.fromkeys(repos, 10)


class Upvotes:
    source = "refresh:hf_upvotes"

    def __init__(self, failing: frozenset[str] = frozenset()) -> None:
        self.failing = failing
        self.asked: list[str] = []

    def upvotes(self, arxiv_id: str) -> int | None:
        self.asked.append(arxiv_id)
        if arxiv_id in self.failing:
            raise SourceUnavailableError(self.source, "down")
        return None if arxiv_id == "2410.00404" else 5


def repo(name: str, days_ago: int) -> Item:
    return make_item(
        item_id=f"gh:o/{name}",
        source_type="github_search",
        kind="repo",
        seen_at=NOW - timedelta(days=days_ago),
    )


def hf_paper(number: str, days_ago: int = 1) -> Item:
    return make_item(
        item_id=f"arxiv:2410.{number}",
        source_type="hf_papers",
        seen_at=NOW - timedelta(days=days_ago),
    )


def stage(  # noqa: PLR0913 - test builder with optional knobs
    tmp_path: Path,
    items: list[Item],
    *,
    stars: Stars | None = None,
    upvotes: Upvotes | None = None,
    cap: int = 1000,
    candidates: tuple[str, ...] = (),
) -> tuple[SignalRefreshStage, Stars | None, Upvotes]:
    store = ItemStore.open(tmp_path)
    for item in items:
        store.upsert(item)
    triage = TriageStore(tmp_path)
    if candidates:
        scored = tuple(
            ScoredItem(item_id=ItemId(c), features=make_features(c), prescore=0.5)
            for c in candidates
        )
        triage.write(make_run("2026-W40", scored))
    up = upvotes or Upvotes()
    cfg = RefreshConfig(horizon_days=180, max_items_per_day=cap)
    built = SignalRefreshStage(
        store,
        SignalStore.open(tmp_path),
        triage,
        RunStore(tmp_path),
        stars=stars,
        upvotes=up,
        cfg=cfg,
        clock=lambda: NOW,
    )
    return built, stars, up


def test_refresh_records_signals(tmp_path: Path) -> None:
    built, stars, up = stage(
        tmp_path,
        [repo("a", 3), hf_paper("00001"), make_item(item_id="arxiv:2410.9")],
        stars=Stars(),
    )
    report = built.run()
    assert stars is not None
    assert stars.asked == ["o/a"]
    assert up.asked == ["2410.00001"]
    assert [(s.source, s.status, s.signals) for s in report.sources] == [
        ("refresh:gh_stars", "ok", 1),
        ("refresh:hf_upvotes", "ok", 1),
    ]
    signals = SignalStore.open(tmp_path)
    assert [s.value for s in signals.history(ItemId("gh:o/a"))] == [10]
    assert (tmp_path / "runs" / "20261010T050000Z-refresh.json").exists()


def test_priority_candidates_first(tmp_path: Path) -> None:
    items = [repo("new", 1), repo("old", 50), repo("mid", 10)]
    built, stars, _ = stage(tmp_path, items, stars=Stars(), cap=2, candidates=("gh:o/old",))
    built.run()
    assert stars is not None
    assert stars.asked == ["o/old", "o/new"]


def test_horizon_respected(tmp_path: Path) -> None:
    built, stars, _ = stage(tmp_path, [repo("ancient", 400), repo("a", 2)], stars=Stars())
    built.run()
    assert stars is not None
    assert stars.asked == ["o/a"]


def test_one_client_failure_isolated(tmp_path: Path) -> None:
    built, _, _ = stage(tmp_path, [repo("a", 2), hf_paper("00001")], stars=Stars(fail=True))
    report = built.run()
    assert [s.status for s in report.sources] == ["failed", "ok"]


def test_partial_and_unknown_papers(tmp_path: Path) -> None:
    papers = [hf_paper("00001"), hf_paper("00002"), hf_paper("00404")]
    built, _, _ = stage(tmp_path, papers, upvotes=Upvotes(frozenset({"2410.00002"})))
    report = built.run()
    hf = report.sources[1]
    assert hf.status == "partial"
    assert hf.received == 1
    assert hf.error is not None
    assert hf.error.startswith("1 failed")
    assert report.sources[0].status == "skipped"  # no stars reader


def test_all_papers_failing(tmp_path: Path) -> None:
    built, _, _ = stage(tmp_path, [hf_paper("00002")], upvotes=Upvotes(frozenset({"2410.00002"})))
    assert built.run().sources[1].status == "failed"


def test_same_day_rerun_adds_nothing(tmp_path: Path) -> None:
    built, _, _ = stage(tmp_path, [repo("a", 2)], stars=Stars())
    built.run()
    assert built.run().sources[0].signals == 0


def test_release_ids_not_refreshed(tmp_path: Path) -> None:
    release = make_item(item_id="gh:o/a@v1", source_type="github_releases", kind="release")
    built, stars, _ = stage(tmp_path, [release], stars=Stars())
    assert built.run().sources[0].status == "skipped"
    assert stars is not None
    assert stars.asked == []


def test_paper_not_on_hf_ignored(tmp_path: Path) -> None:
    arxiv_only = make_item(item_id="arxiv:2410.7")
    hn = Sighting(source="hn", source_type="hackernews", seen_at=NOW, origin_url="x")
    built, _, up = stage(tmp_path, [arxiv_only.model_copy(update={"sightings": (hn,)})])
    built.run()
    assert up.asked == []
