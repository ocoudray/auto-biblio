from datetime import timedelta
from pathlib import Path

from builders import NOW, make_signal

from auto_biblio.store.signals import SignalStore


def test_signal_dedup_same_day(tmp_path: Path) -> None:
    store = SignalStore.open(tmp_path)
    assert store.add([make_signal()]) == 1
    assert store.add([make_signal(value=12, observed_at=NOW + timedelta(hours=3))]) == 0
    assert store.add([make_signal(observed_at=NOW + timedelta(days=1))]) == 1


def test_signal_dedup_survives_reopen(tmp_path: Path) -> None:
    store = SignalStore.open(tmp_path)
    store.add([make_signal()])
    store.flush()
    assert SignalStore.open(tmp_path).add([make_signal()]) == 0


def test_signals_partitioned_by_observed_month_and_sorted(tmp_path: Path) -> None:
    store = SignalStore.open(tmp_path)
    late = make_signal(item_id="gh:a/a", observed_at=NOW + timedelta(hours=1))
    early = make_signal(item_id="gh:b/b")
    old = make_signal(observed_at=NOW - timedelta(days=40))
    store.add([late, early, old])
    store.flush()
    october = (tmp_path / "signals" / "2026-10.jsonl").read_text()
    assert october == f"{early.model_dump_json()}\n{late.model_dump_json()}\n"
    assert (tmp_path / "signals" / "2026-08.jsonl").exists()


def test_flush_without_changes_writes_nothing(tmp_path: Path) -> None:
    SignalStore.open(tmp_path).flush()
    assert not (tmp_path / "signals").exists()
