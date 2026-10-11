from datetime import timedelta
from pathlib import Path

import pytest
from builders import NOW, make_features, make_item, make_run, make_verdict
from fakes import PipelineRunner

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import ConfigError, TriageRunMissingError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item
from auto_biblio.domain.triage import ScoredItem
from auto_biblio.extract import ExtractedText
from auto_biblio.llm import StructuredLLM
from auto_biblio.llm.budgeted import BudgetedRunner
from auto_biblio.llm.cached import CachedLLM
from auto_biblio.llm.chain import FallbackHook, ModelChain
from auto_biblio.repo_config.analysis import AnalysisConfig
from auto_biblio.repo_config.llm import LLMConfig
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.repo_config.profile import Profile
from auto_biblio.repo_config.sources import SourcesConfig
from auto_biblio.stages.analyze import AnalyzeStage
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.llm_cache import LLMCacheStore
from auto_biblio.store.triage import TriageStore

WEEK = "2026-W41"
PROFILE = Profile.model_validate(
    {
        "themes": [
            {"id": "agentic", "label": "Agents", "description": "agent"},
            {"id": "rag", "label": "RAG", "description": "retrieval"},
        ]
    }
)
MODEL = {"id": "t:m", "input_usd_per_mtok": 0, "output_usd_per_mtok": 0, "batch_size": 5}


ROLES = ("triage", "short_note", "deep_analysis", "synthesis")


def llm_config(
    tokens: int = 1_000_000, roles: tuple[str, ...] = ROLES, chain: tuple[str, ...] = ("m",)
) -> LLMConfig:
    return LLMConfig.model_validate(
        {
            "models": {"m": MODEL, "n": MODEL | {"id": "t:n"}},
            "chains": {role: list(chain) for role in roles},
            "weekly_budget": {"usd": 0, "tokens": tokens},
        }
    )


class Extractor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def extract(self, item: Item, max_chars: int) -> ExtractedText:
        self.calls.append(item.id)
        if self.fail:
            return ExtractedText(
                text=item.summary or item.title, source="abstract", errors=("HTTP 404",)
            )
        return ExtractedText(text=f"Full text of {item.title}"[:max_chars], source="full_text")


def scored(item_id: str, final: float, theme: str = "agentic", slot: str = "theme") -> ScoredItem:
    return ScoredItem.model_validate(
        {
            "item_id": item_id,
            "features": make_features(item_id),
            "prescore": 0.5,
            "verdict": make_verdict(scores={theme: 4}),
            "final_score": final,
            "slot": slot,
            "theme": theme,
        }
    )


def seed(tmp_path: Path) -> None:
    items = ItemStore.open(tmp_path)
    items.upsert(
        make_item(
            item_id="arxiv:2410.00001", title="Durable agents", seen_at=NOW - timedelta(days=2)
        )
    )
    items.upsert(
        make_item(
            item_id="arxiv:2410.00002", title="Hybrid retrieval", seen_at=NOW - timedelta(days=2)
        )
    )
    items.upsert(
        make_item(
            item_id="gh:o/r@v2",
            source_type="github_releases",
            kind="release",
            title="r v2",
            seen_at=NOW - timedelta(days=1),
        )
    )
    items.flush()
    TriageStore(tmp_path).write(
        make_run(
            WEEK,
            (
                scored("arxiv:2410.00001", 0.9),
                scored("arxiv:2410.00002", 0.8, theme="rag"),
                scored("gh:o/r@v2", 0.7),
            ),
        )
    )


def build(
    tmp_path: Path,
    *,
    extractor: Extractor | None = None,
    llm: LLMConfig | None = None,
    deep_count: int = 1,
    failing: dict[str, set[str]] | None = None,
) -> tuple[AnalyzeStage, PipelineRunner, Extractor]:
    runner = PipelineRunner(failing)
    cfg = llm or llm_config()
    ext = extractor or Extractor()

    def factory(ledger: BudgetLedger, hook: FallbackHook) -> StructuredLLM:
        return CachedLLM(
            ModelChain(BudgetedRunner(runner, ledger), cfg, hook), LLMCacheStore(tmp_path), cfg
        )

    config = RepoConfig(
        profile=PROFILE,
        sources=SourcesConfig(sources=()),
        analysis=AnalysisConfig(deep_count=deep_count),
        llm=cfg,
    )
    stage = AnalyzeStage(
        config,
        ItemStore.open(tmp_path),
        TriageStore(tmp_path),
        AnalysisStore(tmp_path),
        KBStore.open(tmp_path / "kb"),
        extractor=ext,
        llm_factory=factory,
        clock=lambda: NOW,
    )
    return stage, runner, ext


def kb_snapshot(tmp_path: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in sorted((tmp_path / "kb").rglob("*.md"))
    }


def test_creates_short_and_deep_notes(tmp_path: Path) -> None:
    seed(tmp_path)
    stage, runner, extractor = build(tmp_path)
    run = stage.run(WEEK)
    assert [(o.item_id, o.status, o.depth) for o in run.outcomes] == [
        ("arxiv:2410.00001", "created", "deep"),
        ("arxiv:2410.00002", "created", "short"),
        ("gh:o/r@v2", "created", "short"),
    ]
    assert extractor.calls == ["arxiv:2410.00001"]
    assert runner.calls[:3] == ["short_note", "short_note", "deep_analysis"]  # short notes first
    kb = KBStore.open(tmp_path / "kb")
    repo_note = kb.get(ItemId("gh:o/r"))
    assert repo_note is not None
    assert repo_note.meta.kind == "tool"
    assert repo_note.meta.title == "o/r"
    assert repo_note.meta.url == "https://github.com/o/r"
    deep = kb.get(ItemId("arxiv:2410.00001"))
    assert deep is not None
    assert deep.meta.depth == "deep"
    assert deep.meta.source_text == "full_text"


def test_theme_page_written_and_changelog(tmp_path: Path) -> None:
    seed(tmp_path)
    run = build(tmp_path)[0].run(WEEK)
    assert run.theme == "agentic"
    page = KBStore.open(tmp_path / "kb").read_theme(ThemeId("agentic"))
    assert page is not None
    assert page.meta.notes == ("arxiv:2410.00001", "gh:o/r")
    changelog = (tmp_path / "kb" / "changelog" / f"{WEEK}.md").read_text()
    assert "fiche créée, deep" in changelog
    assert "Page `agentic` réécrite." in changelog
    assert run.changelog.links_added
    assert (tmp_path / "analysis" / f"{WEEK}.json").exists()


def test_rerun_same_week_changes_nothing(tmp_path: Path) -> None:
    seed(tmp_path)
    build(tmp_path)[0].run(WEEK)
    before = kb_snapshot(tmp_path)
    stage, runner, _ = build(tmp_path)
    again = stage.run(WEEK)
    assert runner.calls == []
    assert kb_snapshot(tmp_path) == before
    assert [o.status for o in again.outcomes] == ["created", "created", "created"]
    assert again.theme == "agentic"


def test_short_note_deepened_next_week(tmp_path: Path) -> None:
    seed(tmp_path)
    build(tmp_path, deep_count=0)[0].run(WEEK)
    my_note = tmp_path / "kb" / "notes" / "papers" / "arxiv-2410.00002.md"
    my_note.write_text(my_note.read_text() + "\nMy own comment.\n")
    TriageStore(tmp_path).write(
        make_run("2026-W42", (scored("arxiv:2410.00002", 0.9, theme="rag"),))
    )
    run = build(tmp_path, deep_count=1)[0].run("2026-W42")
    assert run.outcomes[0].status == "deepened"
    assert "My own comment." in my_note.read_text()
    assert "## Méthode" in my_note.read_text()


def test_extraction_failure_gives_short_note(tmp_path: Path) -> None:
    seed(tmp_path)
    run = build(tmp_path, extractor=Extractor(fail=True))[0].run(WEEK)
    assert run.outcomes[0].depth == "short"
    assert run.outcomes[0].source_text == "abstract"
    assert any(
        "full text unavailable for arxiv:2410.00001: HTTP 404" in d for d in run.degradations
    )


def test_budget_exhausted_skips_theme_page(tmp_path: Path) -> None:
    seed(tmp_path)
    run = build(tmp_path, llm=llm_config(tokens=5_000))[0].run(WEEK)
    statuses = [o.status for o in run.outcomes]
    assert statuses.count("created") >= 1
    assert "skipped" in statuses
    assert run.theme is None
    assert any("theme page skipped" in d for d in run.degradations)


def test_failed_note_keeps_existing(tmp_path: Path) -> None:
    seed(tmp_path)
    build(tmp_path, deep_count=0)[0].run(WEEK)
    note = tmp_path / "kb" / "notes" / "papers" / "arxiv-2410.00001.md"
    before = note.read_bytes()
    TriageStore(tmp_path).write(make_run("2026-W42", (scored("arxiv:2410.00001", 0.9),)))
    stage, _, _ = build(tmp_path, llm=llm_config(tokens=1))
    run = stage.run("2026-W42")
    assert run.outcomes[0].status == "skipped"
    assert note.read_bytes() == before


def test_missing_triage_and_roles(tmp_path: Path) -> None:
    with pytest.raises(TriageRunMissingError):
        build(tmp_path)[0].run(WEEK)
    with pytest.raises(ConfigError, match="deep_analysis"):
        build(tmp_path, llm=llm_config(roles=("triage", "short_note")))


def test_failed_models_are_reported(tmp_path: Path) -> None:
    seed(tmp_path)
    failing = {"t:m": {"deep_analysis", "synthesis"}}
    run = build(tmp_path, failing=failing)[0].run(WEEK)
    assert run.outcomes[0].status == "failed"
    assert run.theme is None
    assert any(d.startswith("note arxiv:2410.00001 not written") for d in run.degradations)
    assert any(d.startswith("theme page agentic kept as is") for d in run.degradations)


def test_fallback_model_is_journaled(tmp_path: Path) -> None:
    seed(tmp_path)
    stage, _, _ = build(tmp_path, llm=llm_config(chain=("m", "n")), failing={"t:m": {"short_note"}})
    run = stage.run(WEEK)
    assert [o.status for o in run.outcomes] == ["created", "created", "created"]
    assert "fallback short_note: t:m (ProviderUnavailableError)" in run.degradations


def test_title_only_item_and_theme_without_notes(tmp_path: Path) -> None:
    items = ItemStore.open(tmp_path)
    items.upsert(
        make_item(
            item_id="url:a", source_type="rss", kind="blog_post", title="A post", summary=None
        )
    )
    items.flush()
    TriageStore(tmp_path).write(
        make_run(WEEK, (scored("url:a", 0.9, theme="rag", slot="discovery"),))
    )
    stage, _, _ = build(tmp_path)
    run = stage.run(WEEK)
    assert run.outcomes[0].source_text == "title"
    note = KBStore.open(tmp_path / "kb").get(ItemId("url:a"))
    assert note is not None
    assert note.meta.themes == ("rag",)
    assert run.theme == "rag"
