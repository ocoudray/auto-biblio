from datetime import datetime, timedelta

from builders import NOW, make_item

from auto_biblio.domain.features import FeatureVector, SourceFamily, ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Sighting
from auto_biblio.domain.selection import (
    display_theme,
    final_selection,
    is_excluded,
    is_revenant,
    pick_discoveries,
    preselect,
)
from auto_biblio.domain.triage import ScoredItem, TriageVerdict
from auto_biblio.repo_config.triage import RevenantConfig, TriageConfig

CFG = TriageConfig()
T1, T2 = ThemeId("t1"), ThemeId("t2")
WEIGHTS = {T1: 1.0, T2: 1.0}
WINDOW_START = NOW - timedelta(days=7)


def fv(  # noqa: PLR0913 - test builder
    item_id: str,
    *,
    family: SourceFamily = "paper",
    relevance: float = 0.9,
    popularity: float = 0.5,
    revenant: bool = False,
    pct: dict[ThemeId, float] | None = None,
) -> FeatureVector:
    return FeatureVector(
        item_id=ItemId(item_id),
        family=family,
        context_level="abstract",
        theme_similarity={},
        theme_percentile=pct if pct is not None else {T1: relevance},
        relevance=relevance,
        popularity=popularity,
        source_count=1,
        watched=False,
        revenant=revenant,
        age_days=1,
    )


def test_excluded_whole_word_only() -> None:
    assert is_excluded(make_item(title="Crypto markets and LLMs"), ["crypto"])
    assert not is_excluded(make_item(title="Cryptography for agents"), ["crypto"])
    assert is_excluded(make_item(title="x", summary="about crypto"), ["", "crypto"])
    assert not is_excluded(make_item(title="x", summary=None), [])


def old_item(*, extra_family: bool = False) -> Item:
    item = make_item(source_type="arxiv", seen_at=NOW - timedelta(days=60))
    if not extra_family:
        return item
    hn = Sighting(
        source="hn", source_type="hackernews", seen_at=NOW - timedelta(days=1), origin_url="x"
    )
    return item.model_copy(update={"sightings": (*item.sightings, hn)})


def revenant(item: Item, popularity: float, last_shown: datetime | None = None) -> bool:
    return is_revenant(
        item,
        item_popularity=popularity,
        window_start=WINDOW_START,
        now=NOW,
        cfg=RevenantConfig(),
        last_shown=last_shown,
    )


def test_revenant_by_popularity() -> None:
    assert revenant(old_item(), 0.95)
    assert not revenant(old_item(), 0.5)


def test_revenant_by_new_family() -> None:
    assert revenant(old_item(extra_family=True), 0.1)


def test_revenant_new_family_needs_old_sighting() -> None:
    item = make_item(source_type="hackernews", seen_at=NOW - timedelta(days=1))
    item = item.model_copy(update={"published_at": NOW - timedelta(days=90)})
    assert not revenant(item, 0.1)


def test_revenant_cooldown() -> None:
    assert not revenant(old_item(), 0.99, last_shown=NOW - timedelta(weeks=3))
    assert revenant(old_item(), 0.99, last_shown=NOW - timedelta(weeks=9))


def test_young_item_never_revenant() -> None:
    assert not revenant(make_item(seen_at=NOW - timedelta(days=5)), 1.0)


def prescores(features: list[FeatureVector]) -> dict[ItemId, float]:
    return {f.item_id: f.relevance for f in features}


def test_relevance_gate() -> None:
    features = [fv("a:1", relevance=0.9), fv("a:2", relevance=0.5)]
    assert preselect(features, prescores(features), frozenset(), CFG) == ("a:1",)


def test_family_floor_reserves_slots() -> None:
    papers = [fv(f"p:{i:03}", relevance=0.95) for i in range(200)]
    repos = [fv(f"r:{i}", family="repo", relevance=0.76) for i in range(3)]
    features = papers + repos
    chosen = preselect(features, prescores(features), frozenset(), CFG)
    assert len(chosen) == CFG.candidates
    assert {"r:0", "r:1", "r:2"} <= set(chosen)
    assert chosen[0] == "p:000"


def test_already_shown_skipped_unless_revenant() -> None:
    features = [fv("a:1"), fv("a:2", revenant=True)]
    shown = frozenset({ItemId("a:1"), ItemId("a:2")})
    assert preselect(features, prescores(features), shown, CFG) == ("a:2",)


def test_discoveries_one_per_family() -> None:
    features = [
        fv("d:1", family="discussion", relevance=0.2, popularity=0.99),
        fv("d:2", family="discussion", relevance=0.2, popularity=0.98),
        fv("r:1", family="repo", relevance=0.3, popularity=0.97),
        fv("p:1", relevance=0.2, popularity=0.96),
    ]
    assert pick_discoveries(features, frozenset(), CFG) == ("d:1", "r:1")


def test_discoveries_require_popularity_and_novelty() -> None:
    features = [
        fv("d:1", family="discussion", relevance=0.2, popularity=0.5),
        fv("d:2", family="discussion", relevance=0.9, popularity=0.99),
        fv("d:3", family="discussion", relevance=0.1, popularity=0.99),
    ]
    assert pick_discoveries(features, frozenset({ItemId("d:3")}), CFG) == ()


def verdict(scores: dict[ThemeId, int]) -> TriageVerdict:
    return TriageVerdict(
        ref="i", relevance=scores, item_type="tool", novelty="low", confidence="low", reason="r"
    )


def scored(
    item_id: str,
    final: float,
    scores: dict[ThemeId, int] | None = None,
    *,
    discovery: bool = False,
) -> ScoredItem:
    return ScoredItem(
        item_id=ItemId(item_id),
        features=fv(item_id),
        prescore=0.5,
        verdict=verdict(scores) if scores is not None else None,
        final_score=final,
        discovery=discovery,
    )


def selected_ids(items: tuple[ScoredItem, ...]) -> list[str]:
    return [s.item_id for s in items if s.slot is not None]


def test_llm_gate_drops_offtopic() -> None:
    result = final_selection(
        [scored("a:1", 0.9, {T1: 1}), scored("a:2", 0.5, {T1: 3})], WEIGHTS, CFG
    )
    assert selected_ids(result) == ["a:2"]
    assert len(result) == 2


def test_discovery_bypasses_llm_gate() -> None:
    result = final_selection([scored("d:1", 0.1, {T1: 0}, discovery=True)], WEIGHTS, CFG)
    assert result[0].slot == "discovery"
    assert result[0].theme == T1


def test_per_theme_quota() -> None:
    items = [scored(f"a:{i}", 1 - i / 10, {T1: 5}) for i in range(6)]
    items.append(scored("b:1", 0.1, {T2: 5}))
    result = final_selection(items, WEIGHTS, CFG)
    assert selected_ids(result) == ["a:0", "a:1", "a:2", "a:3", "b:1"]
    assert result[-1].theme == T2


def test_total_quota() -> None:
    cfg = TriageConfig(selected=4, per_theme_max=4)
    items = [scored(f"a:{i}", 1 - i / 10, {T1: 5}) for i in range(3)]
    items += [scored(f"b:{i}", 0.5 - i / 10, {T2: 5}) for i in range(3)]
    assert len(selected_ids(final_selection(items, WEIGHTS, cfg))) == 4


def test_short_digest_not_padded() -> None:
    assert selected_ids(final_selection([scored("a:1", 0.9, {T1: 4})], WEIGHTS, CFG)) == ["a:1"]


def test_unverified_item_uses_features_theme() -> None:
    item = scored("a:1", 0.4)
    assert final_selection([item], WEIGHTS, CFG)[0].theme == T1


def test_display_theme_none_without_theme() -> None:
    item = scored("a:1", 0.4).model_copy(update={"features": fv("a:1", pct={})})
    assert display_theme(item, WEIGHTS) is None
    assert final_selection([item], WEIGHTS, CFG)[0].slot is None


def test_display_theme_uses_weights() -> None:
    item = scored("a:1", 0.4, {T1: 4, T2: 3})
    assert display_theme(item, {T1: 0.5, T2: 1.0}) == T2
