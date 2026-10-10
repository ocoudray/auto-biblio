import os
from pathlib import Path

import pytest

from auto_biblio.store._files import atomic_write_text, read_lines


def test_atomic_write_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b.txt"
    atomic_write_text(target, "hello\n")
    assert target.read_text() == "hello\n"


def test_atomic_write_keeps_old_file_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "data.jsonl"
    target.write_text("old\n")

    def failing_replace(_src: object, _dst: object) -> None:
        message = "disk full"
        raise OSError(message)

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_text(target, "new\n")
    assert target.read_text() == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["data.jsonl"]


def test_read_lines_skips_blank(tmp_path: Path) -> None:
    target = tmp_path / "x.jsonl"
    target.write_text("a\n\nb\n")
    assert read_lines(target) == ["a", "b"]
