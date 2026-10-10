from typing import get_args

import pytest
from builders import NOW, make_item

from auto_biblio.domain.features import (
    FAMILY_OF,
    FeatureVector,
    ThemeId,
    context_level,
    embedding_text,
    families_seen,
    grouped_percentiles,
    item_family,
    multi_source,
    percentile_of,
    percentile_ranks,
)
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Sighting, SourceType


def with_sighting(item: Item, source_type: SourceType) -> Item:
    extra = Sighting(
        source=source_type, source_type=source_type, seen_at=NOW, origin_url="https://x.example"
    )
    return item.model_copy(update={"sightings": (*item.sightings, extra)})


def test_family_of_every_source_type() -> None:
    assert set(FAMILY_OF) == set(get_args(SourceType))


def test_item_family_prefers_text_source() -> None:
    item = with_sighting(make_item(source_type="hackernews", summary="abstract"), "arxiv")
    assert item_family(item) == "paper"
    assert families_seen(item) == {"paper", "discussion"}


def test_item_family_title_only_uses_first_sighting() -> None:
    item = with_sighting(make_item(source_type="hackernews", summary=None), "rss")
    assert item_family(item) == "discussion"


def test_embedding_text_truncates_summary() -> None:
    item = make_item(title="A   title", summary="one two three four")
    assert embedding_text(item, 2) == "A title — one two"


def test_embedding_text_title_only() -> None:
    assert embedding_text(make_item(title="T", summary=None), 30) == "T"
    assert embedding_text(make_item(title="T", summary="x"), 0) == "T"


def test_context_level() -> None:
    assert context_level(make_item(summary="s"), None) == "abstract"
    assert context_level(make_item(summary=None), "snippet") == "snippet"
    assert context_level(make_item(summary=None), None) == "title_only"


def test_percentile_ranks_ties() -> None:
    assert percentile_ranks([1, 2, 2, 3]) == [0, 0.5, 0.5, 1]


def test_percentile_single_and_empty() -> None:
    assert percentile_ranks([4.0]) == [0.5]
    assert percentile_ranks([]) == []


def test_percentile_of() -> None:
    assert percentile_of(5, [1, 2, 3, 4]) == 1.0
    assert percentile_of(0, [1, 2]) == 0.0
    assert percentile_of(2, [1, 2, 3]) == pytest.approx(0.5)
    assert percentile_of(2, []) == 0.5


def test_percentiles_are_per_family() -> None:
    low = {f"p{i}": 0.2 + i * 0.01 for i in range(20)}
    high = {f"d{i}": 0.6 + i * 0.01 for i in range(20)}
    groups = dict.fromkeys(low, "paper") | dict.fromkeys(high, "discussion")
    ranks = grouped_percentiles(low | high, groups, min_population=10)
    assert ranks["p19"] == 1.0
    assert ranks["d19"] == 1.0
    assert ranks["p0"] == 0.0


def test_small_family_falls_back_to_global() -> None:
    values = {"a": 0.1, "b": 0.2, "c": 0.9}
    groups = {"a": "paper", "b": "paper", "c": "repo"}
    ranks = grouped_percentiles(values, groups, min_population=2)
    assert ranks["c"] == 1.0  # global rank: the repo family has a single member
    assert ranks["a"] == 0.0
    assert ranks["b"] == 1.0  # rank within the paper family


def test_multi_source() -> None:
    assert [multi_source(n) for n in (1, 2, 3, 5)] == [0, 0.5, 1, 1]


def test_model_inputs_stable_order() -> None:
    features = FeatureVector(
        item_id=ItemId("arxiv:1"),
        family="repo",
        context_level="snippet",
        theme_similarity={ThemeId("t"): 0.4},
        theme_percentile={ThemeId("t"): 0.9},
        relevance=0.9,
        popularity=0.5,
        source_count=2,
        watched=True,
        revenant=False,
        age_days=3,
    )
    inputs = features.model_inputs(0.8)
    assert list(inputs)[:6] == [
        "relevance",
        "popularity",
        "multi_source",
        "watched",
        "revenant",
        "llm_rel",
    ]
    assert inputs["family_repo"] == 1.0
    assert inputs["family_paper"] == 0.0
    assert inputs["context_snippet"] == 1.0
    assert inputs["multi_source"] == 0.5
