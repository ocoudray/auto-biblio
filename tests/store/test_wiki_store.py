from datetime import date
from pathlib import Path, PurePosixPath

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.wiki.links import Candidate, NoteLinks, WikiLinks
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


def test_assets_include_notebooks_only_from_code(tmp_path: Path) -> None:
    code = tmp_path / "wiki/llm/code"
    (code / ".ipynb_checkpoints").mkdir(parents=True)
    (code / "t.ipynb").write_bytes(b"{}")
    (code / ".ipynb_checkpoints/t-checkpoint.ipynb").write_bytes(b"{}")
    for name in ("t.py", "t.json", "t.pt"):
        (code / name).write_bytes(b"x")
    (tmp_path / "wiki/llm/elsewhere.ipynb").write_bytes(b"{}")
    (tmp_path / "wiki/llm/img").mkdir()
    (tmp_path / "wiki/llm/img/t.ipynb").write_bytes(b"{}")
    assert WikiStore(tmp_path).assets() == {PurePosixPath("llm/code/t.ipynb"): b"{}"}


def test_links_round_trip(tmp_path: Path) -> None:
    store = WikiStore(tmp_path)
    assert store.read_links() == WikiLinks()
    links = WikiLinks(
        notes={ItemId("a:1"): NoteLinks(notions=("llm/attention",), signature="s")},
        candidates={
            "kv cache": Candidate(
                name="KV cache",
                notes=(ItemId("a:1"),),
                first_seen=date(2026, 10, 20),
                last_seen=date(2026, 10, 20),
            )
        },
    )
    store.write_links(links)
    assert (tmp_path / "state/wiki/links.json").exists()
    assert (tmp_path / "state/wiki/candidates.json").exists()
    assert WikiStore(tmp_path).read_links() == links
