from datetime import timedelta

import pytest
from builders import NOW, make_item

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.merge import merge_items, normalized_title


def test_merge_unions_are_sorted_and_deduplicated() -> None:
    a = make_item(links=("gh:b/b", "gh:a/a"), tags=("cs.LG",))
    b = make_item(source_type="hackernews", links=("gh:a/a",), tags=("cs.CL", "cs.LG"))
    merged = merge_items(a, b)
    assert merged.links == (ItemId("gh:a/a"), ItemId("gh:b/b"))
    assert merged.tags == ("cs.CL", "cs.LG")
    assert [s.source for s in merged.sightings] == ["arxiv", "hackernews"]


def test_merge_deduplicates_same_day_sighting() -> None:
    a = make_item()
    again = make_item(seen_at=NOW + timedelta(hours=2))
    assert len(merge_items(a, again).sightings) == 1


def test_merge_is_commutative_on_sets() -> None:
    a = make_item(links=("gh:a/a",), tags=("x",), seen_at=NOW - timedelta(days=3))
    b = make_item(source_type="rss", links=("gh:b/b",), tags=("y",))
    ab, ba = merge_items(a, b), merge_items(b, a)
    assert ab.sightings == ba.sightings
    assert ab.links == ba.links
    assert ab.tags == ba.tags
    assert ab.first_seen == ba.first_seen


def test_merge_keeps_earliest_first_seen() -> None:
    early = make_item(source_type="hackernews", seen_at=NOW - timedelta(days=5))
    late = make_item(seen_at=NOW)
    assert merge_items(late, early).first_seen == NOW - timedelta(days=5)


def test_merge_prefers_higher_priority_source() -> None:
    arxiv = make_item(title="Arxiv title")
    hn = make_item(source_type="hackernews", title="HN title", kind="blog_post")
    assert merge_items(arxiv, hn).title == "Arxiv title"
    assert merge_items(hn, arxiv).title == "Arxiv title"
    assert merge_items(hn, arxiv).kind == "paper"


def test_merge_fills_missing_fields() -> None:
    arxiv = make_item(summary=None)
    rss = make_item(source_type="rss", summary="from rss")
    assert merge_items(arxiv, rss).summary == "from rss"


def test_merge_rejects_different_ids() -> None:
    with pytest.raises(ValueError, match="different"):
        merge_items(make_item(), make_item(item_id="gh:o/r", kind="repo"))


def test_merge_papers_by_normalized_title() -> None:
    a = make_item(item_id="url:0000000000000001", title="Mamba: Linear-Time  Sequence Modeling!")
    b = make_item(
        item_id="url:0000000000000002",
        source_type="rss",
        title="mamba linear-time sequence modeling",
    )
    assert merge_items(a, b).id == ItemId("url:0000000000000001")


def test_normalized_title() -> None:
    assert normalized_title("  Mamba: Linear-Time  Sequence Modeling! ") == (
        "mamba linear-time sequence modeling"
    )
