from datetime import timedelta
from pathlib import Path

from builders import NOW, make_item

from auto_biblio.domain.ids import ItemId
from auto_biblio.store.items import ItemStore


def test_items_roundtrip(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    item = make_item()
    store.upsert(item)
    store.flush()
    assert ItemStore.open(tmp_path).get(item.id) == item


def test_items_partitioned_by_first_seen_month_sorted_by_id(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    b = make_item(item_id="gh:b/b", kind="repo", source_type="github_search")
    a = make_item(item_id="gh:a/a", kind="repo", source_type="github_search")
    older = make_item(item_id="gh:c/c", kind="repo", seen_at=NOW - timedelta(days=40))
    for item in (b, a, older):
        store.upsert(item)
    store.flush()
    october = (tmp_path / "items" / "2026-10.jsonl").read_text()
    assert october == f"{a.model_dump_json()}\n{b.model_dump_json()}\n"
    assert (tmp_path / "items" / "2026-08.jsonl").exists()


def test_flush_is_byte_identical_when_unchanged(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    store.upsert(make_item())
    store.flush()
    path = tmp_path / "items" / "2026-10.jsonl"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    reopened = ItemStore.open(tmp_path)
    assert reopened.upsert(make_item()) == "unchanged"
    reopened.flush()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_upsert_outcomes(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    assert store.upsert(make_item()) == "new"
    assert store.upsert(make_item(source_type="hackernews")) == "merged"
    assert store.upsert(make_item(source_type="hackernews")) == "unchanged"
    item = store.get(ItemId("arxiv:2410.12345"))
    assert item is not None
    assert len(item.sightings) == 2


def test_upsert_matches_paper_by_title(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    store.upsert(make_item(item_id="url:0000000000000001", title="Mamba: Linear-Time!"))
    outcome = store.upsert(
        make_item(item_id="url:0000000000000002", source_type="rss", title="mamba linear-time")
    )
    assert outcome == "merged"
    assert store.get(ItemId("url:0000000000000002")) is None
    store.flush()
    assert len((tmp_path / "items" / "2026-10.jsonl").read_text().splitlines()) == 1


def test_merge_moving_first_seen_month_moves_partition(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    store.upsert(make_item())
    store.flush()
    store.upsert(make_item(source_type="rss", seen_at=NOW - timedelta(days=40)))
    store.flush()
    assert not (tmp_path / "items" / "2026-10.jsonl").exists()
    assert (tmp_path / "items" / "2026-08.jsonl").read_text().count("\n") == 1


def test_distinct_arxiv_papers_with_same_title_are_kept(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    assert store.upsert(make_item(item_id="arxiv:2401.00001", title="Scaling Laws")) == "new"
    assert store.upsert(make_item(item_id="arxiv:2501.00002", title="Scaling laws")) == "new"


def test_title_index_follows_retitled_items(tmp_path: Path) -> None:
    store = ItemStore.open(tmp_path)
    store.upsert(make_item(source_type="hackernews", title="Show HN title"))
    store.upsert(make_item(title="Real arXiv title"))
    outcome = store.upsert(make_item(item_id="url:00000000000000aa", title="Show HN title"))
    assert outcome == "new"
    assert (
        store.upsert(
            make_item(item_id="url:00000000000000bb", source_type="rss", title="real arxiv title")
        )
        == "merged"
    )
