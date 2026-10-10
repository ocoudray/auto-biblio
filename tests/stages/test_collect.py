from datetime import datetime, timedelta
from pathlib import Path

from builders import NOW, make_item, make_signal

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import SourceBatch
from auto_biblio.domain.run_report import RunReport
from auto_biblio.stages.collect import CollectStage
from auto_biblio.store.cursors import CursorStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.signals import SignalStore


class FakeSource:
    def __init__(
        self, name: str, batch: SourceBatch | None = None, error: Exception | None = None
    ) -> None:
        self._name = name
        self._batch = batch or SourceBatch()
        self._error = error
        self.since: list[datetime] = []

    @property
    def name(self) -> str:
        return self._name

    def fetch(self, since: datetime) -> SourceBatch:
        self.since.append(since)
        if self._error is not None:
            raise self._error
        return self._batch


def run(
    state: Path,
    *sources: FakeSource,
    only: set[str] | None = None,
    since: datetime | None = None,
) -> RunReport:
    stage = CollectStage(
        list(sources),
        ItemStore.open(state),
        SignalStore.open(state),
        CursorStore.open(state),
        RunStore(state),
        clock=lambda: NOW,
    )
    return stage.run(only=only, since=since)


def snapshot(state: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(state)): p.read_bytes()
        for folder in ("items", "signals")
        for p in sorted((state / folder).glob("*.jsonl"))
    }


def test_first_run_uses_lookback(tmp_path: Path) -> None:
    source = FakeSource("a")
    run(tmp_path, source)
    assert source.since == [NOW - timedelta(days=7)]


def test_next_run_uses_cursor_minus_overlap(tmp_path: Path) -> None:
    cursors = CursorStore.open(tmp_path)
    cursors.set("a", NOW - timedelta(days=1))
    cursors.flush()
    source = FakeSource("a")
    run(tmp_path, source)
    assert source.since == [NOW - timedelta(days=3)]


def test_explicit_since_wins(tmp_path: Path) -> None:
    source = FakeSource("a")
    explicit = NOW - timedelta(days=30)
    run(tmp_path, source, since=explicit)
    assert source.since == [explicit]


def test_cross_source_merge(tmp_path: Path) -> None:
    arxiv = FakeSource("arxiv", SourceBatch(items=(make_item(),)))
    hf = FakeSource("hf", SourceBatch(items=(make_item(source_type="hf_papers", source="hf"),)))
    hn = FakeSource("hn", SourceBatch(items=(make_item(source_type="hackernews", source="hn"),)))
    report = run(tmp_path, arxiv, hf, hn)
    item = ItemStore.open(tmp_path).get(ItemId("arxiv:2410.12345"))
    assert item is not None
    assert len(item.sightings) == 3
    counts = [(s.source, s.new, s.merged) for s in report.sources]
    assert counts == [("arxiv", 1, 0), ("hf", 0, 1), ("hn", 0, 1)]


def test_failing_source_isolated(tmp_path: Path) -> None:
    broken = FakeSource("broken", error=SourceUnavailableError("broken", "HTTP 503"))
    fine = FakeSource("fine", SourceBatch(items=(make_item(),), signals=(make_signal(),)))
    report = run(tmp_path, broken, fine)
    statuses = {s.source: (s.status, s.error) for s in report.sources}
    assert statuses["broken"] == ("failed", "broken: HTTP 503")
    assert statuses["fine"] == ("ok", None)
    cursors = CursorStore.open(tmp_path)
    assert cursors.get("broken") is None
    assert cursors.get("fine") == NOW
    assert ItemStore.open(tmp_path).get(ItemId("arxiv:2410.12345")) is not None


def test_payload_error_quarantined(tmp_path: Path) -> None:
    error = SourcePayloadError("bad", "unexpected", "<html>")
    report = run(tmp_path, FakeSource("bad", error=error))
    quarantined = list((tmp_path / "quarantine").rglob("bad.txt"))
    assert [p.read_text() for p in quarantined] == ["<html>"]
    assert report.sources[0].status == "failed"


def test_only_filter_marks_skipped(tmp_path: Path) -> None:
    a, b = FakeSource("a"), FakeSource("b")
    report = run(tmp_path, a, b, only={"b"})
    assert [(s.source, s.status) for s in report.sources] == [("a", "skipped"), ("b", "ok")]
    assert a.since == []


def test_report_written(tmp_path: Path) -> None:
    run(tmp_path, FakeSource("a"))
    assert (tmp_path / "runs" / "20261010T050000Z-collect.json").exists()


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    def sources() -> list[FakeSource]:
        batch = SourceBatch(items=(make_item(),), signals=(make_signal(),))
        hn = SourceBatch(items=(make_item(source_type="hackernews", source="hn"),))
        return [FakeSource("arxiv", batch), FakeSource("hn", hn)]

    run(tmp_path, *sources())
    first = snapshot(tmp_path)
    run(tmp_path, *sources())
    assert first
    assert snapshot(tmp_path) == first


def test_empty_batch_writes_nothing(tmp_path: Path) -> None:
    report = run(tmp_path, FakeSource("a"))
    assert not (tmp_path / "items").exists()
    assert not (tmp_path / "signals").exists()
    assert report.sources[0].status == "ok"
    assert CursorStore.open(tmp_path).get("a") == NOW


def test_unexpected_error_fails_only_that_source(tmp_path: Path) -> None:
    crashing = FakeSource("crashing", error=ValueError("bad entry"))
    fine = FakeSource("fine", SourceBatch(items=(make_item(),)))
    report = run(tmp_path, crashing, fine)
    statuses = {s.source: s.status for s in report.sources}
    assert statuses == {"crashing": "failed", "fine": "ok"}
    assert ItemStore.open(tmp_path).get(ItemId("arxiv:2410.12345")) is not None
