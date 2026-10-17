from pathlib import Path

from builders import NOW, make_note
from fakes import PipelineRunner

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.llm import StructuredLLM
from auto_biblio.llm.budgeted import BudgetedRunner
from auto_biblio.llm.chain import FallbackHook, ModelChain
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.stages.wiki_link import WikiLinkReport, WikiLinkStage
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.triage import TriageStore
from auto_biblio.store.wiki import WikiStore

MODEL = {"id": "t:m", "input_usd_per_mtok": 0, "output_usd_per_mtok": 0, "batch_size": 2}
CONFIG = RepoConfig.model_validate(
    {
        "profile": {"themes": [{"id": "agentic", "label": "Agents", "description": "a"}]},
        "sources": {"sources": [{"name": "hn", "type": "hackernews"}]},
        "llm": {
            "models": {"m": MODEL},
            "chains": {"wiki_link": ["m"]},
            "weekly_budget": {"usd": 0, "tokens": 1_000_000},
        },
    }
)
INDEX = "---\ntitle: LLM\norder: [llm/attention, llm/kv-cache]\n---\n\nIntro.\n"


def page(title: str) -> str:
    return f"---\ntitle: {title}\nupdated_at: 2026-10-20\n---\n\n# {title}\n\nR.\n"


def setup(
    tmp_path: Path, *, wiki: bool = True, failing: bool = False
) -> tuple[WikiLinkStage, PipelineRunner]:
    kb = KBStore.open(tmp_path / "kb")
    for i in range(3):
        kb.write_note(make_note(f"a:{i}"))
    if wiki:
        (tmp_path / "wiki/llm").mkdir(parents=True)
        (tmp_path / "wiki/llm/index.md").write_text(INDEX)
        (tmp_path / "wiki/llm/attention.md").write_text(page("Attention"))
    runner = PipelineRunner({"t:m": {"wiki_link"}} if failing else None)

    def factory(ledger: BudgetLedger, hook: FallbackHook) -> StructuredLLM:
        assert CONFIG.llm is not None
        return ModelChain(BudgetedRunner(runner, ledger), CONFIG.llm, hook)

    stage = WikiLinkStage(
        CONFIG,
        KBStore.open(tmp_path / "kb"),
        WikiStore(tmp_path),
        TriageStore(tmp_path / "state"),
        AnalysisStore(tmp_path / "state"),
        llm_factory=factory,
        clock=lambda: NOW,
    )
    return stage, runner


def test_links_and_candidates_are_written(tmp_path: Path) -> None:
    stage, runner = setup(tmp_path)
    report = stage.run()
    assert report == WikiLinkReport(processed=3, linked=3, candidates=1, degradations=())
    assert runner.calls == ["wiki_link", "wiki_link"]  # batches of 2
    links = WikiStore(tmp_path).read_links()
    assert {n.notions for n in links.notes.values()} == {("llm/attention",)}
    assert links.candidates["kv cache"].count == 3


def test_nothing_to_do_when_up_to_date(tmp_path: Path) -> None:
    stage, runner = setup(tmp_path)
    stage.run()
    runner.calls.clear()
    assert stage.run().processed == 0
    assert runner.calls == []


def test_new_page_retags_everything(tmp_path: Path) -> None:
    stage, runner = setup(tmp_path)
    stage.run()
    (tmp_path / "wiki/llm/kv-cache.md").write_text(page("KV cache"))
    runner.calls.clear()
    assert stage.run().processed == 3
    links = WikiStore(tmp_path).read_links()
    assert "kv cache" not in links.candidates  # now a notion


def test_failed_batch_is_retried_next_week(tmp_path: Path) -> None:
    stage, _ = setup(tmp_path, failing=True)
    report = stage.run()
    assert report.processed == 0
    assert sum("batch not linked" in d for d in report.degradations) == 2
    assert WikiStore(tmp_path).read_links().notes == {}


def test_without_wiki_nothing_happens(tmp_path: Path) -> None:
    stage, runner = setup(tmp_path, wiki=False)
    assert stage.run() == WikiLinkReport()
    assert runner.calls == []
    assert not (tmp_path / "state/wiki").exists()
