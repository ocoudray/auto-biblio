from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from builders import NOW, make_features, make_item, make_run, make_signal
from fakes import FakeRunner
from pydantic import BaseModel

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import (
    BudgetExhaustedError,
    ChainExhaustedError,
    ConfigError,
    EmbeddingError,
)
from auto_biblio.domain.feedback import FeedbackEvent
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item, Signal
from auto_biblio.domain.triage import ScoredItem, TriageRun
from auto_biblio.embeddings import Vector
from auto_biblio.llm import LLMResult, LLMTask, StructuredLLM
from auto_biblio.llm.budgeted import BudgetedRunner
from auto_biblio.llm.cached import CachedLLM
from auto_biblio.llm.chain import FallbackHook, ModelChain
from auto_biblio.repo_config.llm import LLMConfig
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.repo_config.profile import Profile
from auto_biblio.repo_config.sources import SourcesConfig
from auto_biblio.repo_config.triage import TriageConfig
from auto_biblio.stages.triage import TriageStage, iso_week
from auto_biblio.store.feedback import FeedbackStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.llm_cache import LLMCacheStore
from auto_biblio.store.signals import SignalStore
from auto_biblio.store.triage import TriageStore

WEEK = "2026-W41"
PROFILE = Profile.model_validate(
    {
        "themes": [
            {"id": "agentic", "label": "Agents", "description": "agent", "keywords": ["agent"]},
            {"id": "rag", "label": "RAG", "description": "retrieval", "keywords": ["retrieval"]},
        ],
        "global_exclude": ["crypto"],
    }
)
LLM = LLMConfig.model_validate(
    {
        "models": {
            "m": {"id": "t:m", "input_usd_per_mtok": 0, "output_usd_per_mtok": 0, "batch_size": 4}
        },
        "chains": {"triage": ["m"]},
        "weekly_budget": {"usd": 0, "tokens": 1_000_000},
    }
)
TOPICS = ("agent", "retrieval")


class TopicEmbedder:
    """One axis per topic word, plus a 'nothing' axis: similarity follows the words."""

    model_id = "fake/topics"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        if self.fail:
            msg = "no model"
            raise EmbeddingError(msg)
        return [self._vector(t.lower()) for t in texts]

    @staticmethod
    def _vector(text: str) -> Vector:
        hits = [float(topic in text) for topic in TOPICS]
        raw = [*hits, 1.0 if not any(hits) else 0.2]
        norm = sum(x * x for x in raw) ** 0.5
        return tuple(x / norm for x in raw)


class FailingLLM:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run[T: BaseModel](self, task: LLMTask[T]) -> LLMResult[T]:
        assert task.role == "triage"
        raise self.error


class Context:
    def fetch_many(self, items: Sequence[Item]) -> dict[ItemId, str]:
        return {i.id: "An agent snippet." for i in items}


def corpus() -> list[Item]:
    week_ago = NOW - timedelta(days=3)
    papers = [
        ("arxiv:2410.00001", "Agent harness design"),
        ("arxiv:2410.00002", "Multi-agent memory"),
        ("arxiv:2410.00003", "Hybrid retrieval at scale"),
        ("arxiv:2410.00004", "Protein folding"),
        ("arxiv:2410.00005", "Galaxy surveys"),
        ("arxiv:2410.00006", "Crypto agent markets"),
        ("arxiv:2410.00007", "Agent hype everywhere"),
        ("arxiv:2410.00008", "Weather nowcasting"),
    ]
    items = [make_item(item_id=i, title=t, seen_at=week_ago) for i, t in papers]
    items.append(
        make_item(
            item_id="url:hn1",
            source_type="hackernews",
            title="Show HN: an agent runtime",
            summary=None,
            kind="discussion",
            seen_at=week_ago,
        )
    )
    items += [
        make_item(
            item_id=f"gh:o/repo{i}",
            source_type="github_search",
            kind="repo",
            title=f"Game engine {i}",
            seen_at=week_ago,
        )
        for i in range(20)
    ]
    return items


def build(  # noqa: PLR0913 - test builder with optional knobs
    tmp_path: Path,
    *,
    llm: Callable[[BudgetLedger, FallbackHook], StructuredLLM] | None = None,
    embedder: TopicEmbedder | None = None,
    triage: TriageConfig | None = None,
    items: list[Item] | None = None,
    extra_signals: Sequence[Signal] = (),
) -> tuple[TriageStage, FakeRunner]:
    store = ItemStore.open(tmp_path)
    for item in items if items is not None else corpus():
        store.upsert(item)
    signals = SignalStore.open(tmp_path)
    signals.add(
        make_signal(
            item_id=f"gh:o/repo{i}", value=10 * (i + 1), observed_at=NOW - timedelta(days=1)
        )
        for i in range(20)
    )
    signals.add(extra_signals)
    config = RepoConfig(
        profile=PROFILE,
        sources=SourcesConfig(sources=()),
        triage=triage or TriageConfig(min_family_population=5, relevance_gate=0.7),
        llm=LLM,
    )
    runner = FakeRunner()

    def default_llm(ledger: BudgetLedger, hook: FallbackHook) -> StructuredLLM:
        chain = ModelChain(BudgetedRunner(runner, ledger), LLM, hook)
        return CachedLLM(chain, LLMCacheStore(tmp_path), LLM)

    stage = TriageStage(
        config,
        store,
        signals,
        FeedbackStore.open(tmp_path),
        TriageStore(tmp_path),
        embedder=embedder or TopicEmbedder(),
        llm_factory=llm or default_llm,
        context=Context(),
        clock=lambda: NOW,
    )
    return stage, runner


def selected(run: TriageRun) -> dict[str, str | None]:
    return {s.item_id: s.slot for s in run.items if s.slot is not None}


def test_iso_week() -> None:
    assert iso_week(NOW) == WEEK


def test_run_writes_journal_with_rejected_candidates(tmp_path: Path) -> None:
    run = build(tmp_path)[0].run()
    assert TriageStore(tmp_path).read(WEEK) == run
    chosen = selected(run)
    assert "arxiv:2410.00001" in chosen
    assert "arxiv:2410.00003" in chosen
    hype = next(s for s in run.items if s.item_id == "arxiv:2410.00007")
    assert hype.slot is None  # the LLM said 0: kept in the journal, not selected
    assert "arxiv:2410.00006" not in {s.item_id for s in run.items}  # excluded (crypto)
    assert run.scoring.version == "fixed-v1"
    assert run.usage
    assert run.degradations == ()


def test_title_only_item_gets_snippet_context(tmp_path: Path) -> None:
    run = build(tmp_path)[0].run()
    hn = next(s for s in run.items if s.item_id == "url:hn1")
    assert hn.features.context_level == "snippet"
    assert hn.verdict is not None


def test_discoveries_present(tmp_path: Path) -> None:
    run = build(tmp_path)[0].run()
    discoveries = [s for s in run.items if s.slot == "discovery"]
    assert [s.item_id for s in discoveries] == ["gh:o/repo19"]


def test_selection_grouped_and_capped(tmp_path: Path) -> None:
    cfg = TriageConfig(min_family_population=5, relevance_gate=0.7, per_theme_max=1, selected=2)
    run = build(tmp_path, triage=cfg)[0].run()
    themes = [s.theme for s in run.items if s.slot == "theme"]
    assert sorted(t for t in themes if t is not None) == ["agentic", "rag"]


def test_llm_down_still_produces_run(tmp_path: Path) -> None:
    error = ChainExhaustedError("triage", ("t:m: down",))
    run = build(tmp_path, llm=lambda _l, _h: FailingLLM(error))[0].run()
    assert all(s.verdict is None for s in run.items)
    assert any(d.startswith("batch not triaged") for d in run.degradations)
    assert selected(run)


def test_budget_exhausted_marks_unverified(tmp_path: Path) -> None:
    error = BudgetExhaustedError("tokens", 10, 0)
    run = build(tmp_path, llm=lambda _l, _h: FailingLLM(error))[0].run()
    assert len([d for d in run.degradations if d.startswith("budget exhausted")]) == 1
    assert all(s.llm_rel is None for s in run.items)


def test_embedding_failure_uses_keywords(tmp_path: Path) -> None:
    run = build(tmp_path, embedder=TopicEmbedder(fail=True))[0].run()
    assert any(d.startswith("embedding fallback") for d in run.degradations)
    assert "arxiv:2410.00001" in selected(run)


def test_rerun_same_week_is_free(tmp_path: Path) -> None:
    stage, runner = build(tmp_path)
    first = stage.run()
    calls = runner.calls
    second = stage.run()
    assert runner.calls == calls
    assert all(u.cached for u in second.usage)
    assert selected(second) == selected(first)


def test_shown_items_not_repeated(tmp_path: Path) -> None:
    shown = ScoredItem(
        item_id=ItemId("arxiv:2410.00001"),
        features=make_features("arxiv:2410.00001"),
        prescore=0.5,
        slot="theme",
    )
    TriageStore(tmp_path).write(make_run("2026-W40", (shown,), NOW - timedelta(days=7)))
    run = build(tmp_path)[0].run()
    assert "arxiv:2410.00001" not in {s.item_id for s in run.items}


def test_learned_scoring_used_when_enough_feedback(tmp_path: Path) -> None:
    store = TriageStore(tmp_path)
    feedback = FeedbackStore.open(tmp_path)
    for week in range(6):
        when = NOW - timedelta(weeks=week + 3)
        shown: list[ScoredItem] = []
        for i in range(12):
            item_id = f"arxiv:2409.{week:02}{i:03}"
            relevance = i / 11
            shown.append(
                ScoredItem(
                    item_id=ItemId(item_id),
                    features=make_features(item_id, relevance=relevance),
                    prescore=relevance,
                    llm_rel=relevance,
                    slot="theme",
                )
            )
            feedback.add(
                FeedbackEvent.model_validate(
                    {
                        "item_id": item_id,
                        "polarity": 1 if relevance > 0.5 else -1,
                        "channel": "explicit",
                        "at": when + timedelta(days=1),
                        "digest_week": None,
                        "origin": f"issue#{week}-{i}",
                    }
                )
            )
        store.write(make_run(f"2026-W{30 + week}", tuple(shown), when))
    feedback.flush()
    run = build(tmp_path)[0].run()
    assert run.scoring.version.startswith("learned-")
    assert run.scoring.reliable_labels == 72
    assert run.scoring.coefficients["relevance"] > 0


def test_missing_llm_config_fails_fast(tmp_path: Path) -> None:
    config = RepoConfig(profile=PROFILE, sources=SourcesConfig(sources=()))
    with pytest.raises(ConfigError, match=r"llm\.yaml"):
        TriageStage(
            config,
            ItemStore.open(tmp_path),
            SignalStore.open(tmp_path),
            FeedbackStore.open(tmp_path),
            TriageStore(tmp_path),
            embedder=TopicEmbedder(),
            llm_factory=lambda _l, _h: FailingLLM(RuntimeError()),
            context=Context(),
            clock=lambda: NOW,
        )


def test_old_popular_item_comes_back(tmp_path: Path) -> None:
    old = make_item(
        item_id="gh:o/agent-classic",
        source_type="github_search",
        kind="repo",
        title="Agent classic framework",
        seen_at=NOW - timedelta(days=90),
    )
    history = [
        make_signal(item_id=old.id, value=100, observed_at=NOW - timedelta(days=60)),
        make_signal(item_id=old.id, value=5_000_000, observed_at=NOW - timedelta(hours=1)),
    ]
    run = build(tmp_path, items=[*corpus(), old], extra_signals=history)[0].run()
    back = next(s for s in run.items if s.item_id == "gh:o/agent-classic")
    assert back.features.revenant


def test_fallbacks_are_journaled(tmp_path: Path) -> None:
    def factory(_ledger: BudgetLedger, hook: FallbackHook) -> StructuredLLM:
        hook("triage", "t:m", "ProviderQuotaError")
        return FailingLLM(ChainExhaustedError("triage", ()))

    run = build(tmp_path, llm=factory)[0].run()
    assert "fallback triage: t:m (ProviderQuotaError)" in run.degradations
