from pathlib import Path, PurePosixPath

from builders import make_features, make_item, make_note, make_run, make_verdict

from auto_biblio.domain.triage import ScoredItem
from auto_biblio.domain.website.plan import SitePlan
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.repo_config.site import SiteConfig
from auto_biblio.stages.site import SiteStage
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.triage import TriageStore

CONFIG = RepoConfig.model_validate(
    {
        "profile": {"themes": [{"id": "agentic", "label": "Agents", "description": "a"}]},
        "sources": {"sources": [{"name": "hn", "type": "hackernews"}]},
        "site": SiteConfig(title="Ma veille"),
    }
)


class RecordingBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[SitePlan, str, Path]] = []

    def build(self, plan: SitePlan, title: str, out: Path, /) -> None:
        self.calls.append((plan, title, out))


def seeded(tmp_path: Path) -> tuple[SiteStage, RecordingBuilder]:
    state = tmp_path / "state"
    items = ItemStore.open(state)
    items.upsert(make_item(title="Agent harness"))
    items.flush()
    scored = ScoredItem(
        item_id=make_item().id,
        features=make_features(),
        prescore=0.5,
        verdict=make_verdict(),
        final_score=0.9,
        slot="theme",
        theme="agentic",  # pyright: ignore[reportArgumentType] - ThemeId at runtime
    )
    TriageStore(state).write(make_run("2026-W41", (scored,)))
    kb = KBStore.open(tmp_path / "kb")
    kb.write_note(make_note(str(make_item().id), depth="deep"))
    builder = RecordingBuilder()
    stage = SiteStage(
        CONFIG,
        KBStore.open(tmp_path / "kb"),
        TriageStore(state),
        ItemStore.open(state),
        AnalysisStore(state),
        builder=builder,
    )
    return stage, builder


def test_stage_plans_and_builds(tmp_path: Path) -> None:
    stage, builder = seeded(tmp_path)
    plan = stage.run(tmp_path / "out")
    assert builder.calls == [(plan, "Ma veille", tmp_path / "out")]
    digest = plan.pages[PurePosixPath("digests/2026-W41.md")]
    assert "# Digest — 2026-W41" in digest
    assert "[fiche](../notes/papers/arxiv-2410.12345.md)" in digest
    assert PurePosixPath("notes/papers/arxiv-2410.12345.md") in plan.pages
    assert plan.pages[PurePosixPath("index.md")].startswith("# Ma veille")
