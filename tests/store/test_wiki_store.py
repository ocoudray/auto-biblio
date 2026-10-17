from pathlib import Path, PurePosixPath

from auto_biblio.store.wiki import WikiStore


def test_files_and_assets(tmp_path: Path) -> None:
    store = WikiStore(tmp_path)
    assert not store.exists()
    assert store.files() == {}
    (tmp_path / "wiki/llm/img").mkdir(parents=True)
    (tmp_path / "wiki/GUIDE.md").write_text("g")
    (tmp_path / "wiki/llm/attention.md").write_text("a")
    (tmp_path / "wiki/llm/img/w.svg").write_bytes(b"<svg/>")
    (tmp_path / "wiki/llm/img/w.py").write_text("print()")
    assert store.exists()
    assert store.files() == {
        PurePosixPath("GUIDE.md"): "g",
        PurePosixPath("llm/attention.md"): "a",
    }
    assert store.assets() == {PurePosixPath("llm/img/w.svg"): b"<svg/>"}
