from pathlib import Path, PurePosixPath

from builders import make_features, make_item, make_note, make_run, make_verdict

from auto_biblio.domain.triage import ScoredItem
from auto_biblio.domain.website.plan import SitePlan
from auto_biblio.domain.wiki.links import NoteLinks, WikiLinks
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.repo_config.site import SiteConfig
from auto_biblio.stages.site import SiteStage
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.triage import TriageStore
from auto_biblio.store.wiki import WikiStore

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


def seeded(tmp_path: Path, wiki: WikiStore | None = None) -> tuple[SiteStage, RecordingBuilder]:
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
        wiki=wiki,
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


def test_stage_publishes_the_wiki(tmp_path: Path) -> None:
    domain = tmp_path / "wiki" / "llm"
    (domain / "img").mkdir(parents=True)
    (domain / "index.md").write_text("---\ntitle: LLM\norder: [llm/attention]\n---\n\nI.\n")
    (domain / "attention.md").write_text(
        "---\ntitle: Attention\nupdated_at: 2026-10-20\n---\n\n# Attention\n\nR.\n"
    )
    (domain / "img" / "a.svg").write_bytes(b"<svg/>")
    (domain / "code").mkdir()
    (domain / "code" / "a.ipynb").write_bytes(b"{}")
    (domain / "code" / "a.py").write_bytes(b"print()")
    wiki = WikiStore(tmp_path)
    wiki.write_links(
        WikiLinks(notes={make_item().id: NoteLinks(notions=("llm/attention",), signature="s")})
    )
    stage, _ = seeded(tmp_path, wiki=wiki)
    plan = stage.run(tmp_path / "out")
    assert PurePosixPath("wiki/llm/attention.md") in plan.pages
    assert plan.assets == {
        PurePosixPath("wiki/llm/img/a.svg"): b"<svg/>",
        PurePosixPath("wiki/llm/code/a.ipynb"): b"{}",
    }
    note = plan.pages[PurePosixPath("notes/papers/arxiv-2410.12345.md")]
    assert "> Notions : [Attention](../../wiki/llm/attention.md)" in note
