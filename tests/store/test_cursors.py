import json
from datetime import timedelta
from pathlib import Path

from builders import NOW

from auto_biblio.store.cursors import CursorStore


def test_cursors_roundtrip(tmp_path: Path) -> None:
    store = CursorStore.open(tmp_path)
    assert store.get("hn") is None
    store.set("hn", NOW)
    store.set("arxiv", NOW - timedelta(days=1))
    store.flush()
    raw = (tmp_path / "cursors.json").read_text()
    assert list(json.loads(raw)) == ["arxiv", "hn"]
    assert json.loads(raw)["hn"] == "2026-10-10T05:00:00Z"
    assert CursorStore.open(tmp_path).get("hn") == NOW
