from datetime import timedelta

import pytest
from builders import NOW, make_item, make_signal

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.featurize import (
    FeatureInputs,
    ProfileView,
    build_features,
    keyword_similarities,
)
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Sighting
from auto_biblio.repo_config.profile import Profile
from auto_biblio.repo_config.triage import TriageConfig

A = ThemeId("agentic")
PROFILE = Profile.model_validate(
    {
        "themes": [
            {
                "id": "agentic",
                "label": "Agents",
                "weight": 0.5,
                "description": "Agents.",
                "keywords": ["MCP", "agent"],
                "exclude": ["robotics"],
                "watch": {"repos": ["Pydantic/Pydantic-AI"], "authors": ["Jane Doe"]},
            }
        ],
        "global_exclude": ["crypto"],
    }
)
VIEW = ProfileView.of(PROFILE)
CFG = TriageConfig(min_family_population=1)
WINDOW_START = NOW - timedelta(days=7)


def inputs(pool: list[Item], sims: dict[str, float], **extra: object) -> FeatureInputs:
    base: dict[str, object] = {
        "population": pool,
        "pool": pool,
        "similarities": {ItemId(k): {A: v} for k, v in sims.items()},
        "histories": {},
        "last_shown": {},
        "window_start": WINDOW_START,
        "now": NOW,
    }
    return FeatureInputs(**(base | extra))  # pyright: ignore[reportArgumentType] - test helper


def test_profile_view() -> None:
    assert VIEW.weights == {A: 0.5}
    assert VIEW.exclusions == ("crypto", "robotics")
    assert VIEW.is_watched(make_item(item_id="gh:pydantic/pydantic-ai@v1", kind="release"))
    jane = make_item().model_copy(update={"authors": ("jane doe",)})
    assert VIEW.is_watched(jane)
    assert not VIEW.is_watched(make_item())


def test_keyword_similarities() -> None:
    assert keyword_similarities(make_item(title="An MCP server"), VIEW) == {A: 1.0}
    assert keyword_similarities(make_item(title="Agentic", summary=None), VIEW) == {A: 0.0}


def test_relevance_from_family_percentiles() -> None:
    pool = [make_item(item_id="arxiv:1"), make_item(item_id="arxiv:2")]
    features = build_features(inputs(pool, {"arxiv:1": 0.9, "arxiv:2": 0.1}), VIEW, CFG)
    assert features[ItemId("arxiv:1")].theme_percentile == {A: 1.0}
    assert features[ItemId("arxiv:1")].relevance == pytest.approx(0.5)  # weight 0.5
    assert features[ItemId("arxiv:2")].relevance == 0.0
    assert features[ItemId("arxiv:1")].popularity == 0.5  # no signal: neutral


def test_popularity_ranks_velocities() -> None:
    pool = [
        make_item(item_id="gh:o/a", source_type="github_search", kind="repo"),
        make_item(item_id="gh:o/b", source_type="github_search", kind="repo"),
    ]
    histories = {
        ItemId("gh:o/a"): [make_signal(item_id="gh:o/a", value=1000)],
        ItemId("gh:o/b"): [make_signal(item_id="gh:o/b", value=10)],
    }
    built = build_features(
        inputs(pool, {"gh:o/a": 0.5, "gh:o/b": 0.5}, histories=histories), VIEW, CFG
    )
    assert built[ItemId("gh:o/a")].popularity > built[ItemId("gh:o/b")].popularity


def test_old_items_kept_only_as_revenants() -> None:
    old_quiet = make_item(item_id="arxiv:old", seen_at=NOW - timedelta(days=90))
    old_back = make_item(item_id="arxiv:back", seen_at=NOW - timedelta(days=90))
    hn = Sighting(source="hn", source_type="hackernews", seen_at=NOW, origin_url="x")
    old_back = old_back.model_copy(update={"sightings": (*old_back.sightings, hn)})
    pool = [old_quiet, old_back]
    built = build_features(inputs(pool, {"arxiv:old": 0.5, "arxiv:back": 0.5}), VIEW, CFG)
    assert list(built) == ["arxiv:back"]
    assert built[ItemId("arxiv:back")].revenant
    assert built[ItemId("arxiv:back")].source_count == 2
    assert built[ItemId("arxiv:back")].age_days == pytest.approx(90)


def test_item_without_similarity_gets_no_relevance() -> None:
    built = build_features(inputs([make_item(item_id="arxiv:1")], {}), VIEW, CFG)
    assert built[ItemId("arxiv:1")].relevance == 0.0
