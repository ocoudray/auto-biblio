from pathlib import Path

from builders import make_run

from auto_biblio.store.triage import TriageStore


def test_triage_roundtrip(tmp_path: Path) -> None:
    store = TriageStore(tmp_path)
    run = make_run("2026-W41", ())
    path = store.write(run)
    assert path == tmp_path / "triage" / "2026-W41.json"
    assert store.read("2026-W41") == run
    assert store.read("2026-W40") is None


def test_triage_all_and_latest(tmp_path: Path) -> None:
    store = TriageStore(tmp_path)
    assert store.latest() is None
    assert store.all() == ()
    store.write(make_run("2026-W41", ()))
    store.write(make_run("2026-W39", ()))
    assert [r.week for r in store.all()] == ["2026-W39", "2026-W41"]
    latest = store.latest()
    assert latest is not None
    assert latest.week == "2026-W41"
