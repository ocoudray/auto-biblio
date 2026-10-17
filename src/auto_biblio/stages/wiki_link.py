"""Weekly `wiki link`: tag the notes with the notions of the wiki and collect the missing ones."""

import logging
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import BudgetExhaustedError, ChainExhaustedError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.notes import Note
from auto_biblio.domain.models import Clock
from auto_biblio.domain.wiki.catalog import CatalogEntry, catalog, signature
from auto_biblio.domain.wiki.links import LinkResult, merge_links, stale_notes
from auto_biblio.domain.wiki.pages import load_wiki
from auto_biblio.llm import StructuredLLM
from auto_biblio.llm.prompts.wiki_link_v1 import to_inputs, to_results, wiki_link_task
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.stages.triage import LLMFactory, iso_week
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.triage import TriageStore
from auto_biblio.store.wiki import WikiStore

logger = logging.getLogger(__name__)


class WikiLinkReport(BaseModel):
    """What one run of `wiki link` did."""

    model_config = ConfigDict(frozen=True)

    processed: int = 0
    """Notes tagged during this run."""
    linked: int = 0
    """Notes linked to at least one notion, in total."""
    candidates: int = 0
    """Concepts without a page, in total."""
    degradations: tuple[str, ...] = ()


class WikiLinkStage:
    """Tags the notes whose tagging is missing or outdated, then saves links and candidates."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        config: RepoConfig,
        kb: KBStore,
        wiki: WikiStore,
        triage: TriageStore,
        analyses: AnalysisStore,
        *,
        llm_factory: LLMFactory,
        clock: Clock,
    ) -> None:
        """Build the stage.

        Args:
            config: The data repository configuration (`llm.yaml` needed once a wiki exists).
            kb: The knowledge base.
            wiki: The wiki and its link state.
            triage: Weekly journals, for the budget already spent.
            analyses: Analysis journals, for the budget already spent.
            llm_factory: Builds the LLM of the run from its budget ledger and fallback hook.
            clock: Current time provider.
        """
        self._config = config
        self._kb = kb
        self._wiki = wiki
        self._triage = triage
        self._analyses = analyses
        self._llm_factory = llm_factory
        self._clock = clock

    def run(self, week: str | None = None) -> WikiLinkReport:
        """Tag the notes and write `state/wiki/`.

        Args:
            week: ISO week whose budget the calls are charged to (default: the current one).

        Returns:
            The report; without `wiki/`, an empty one and nothing written.
        """
        if not self._wiki.exists():
            return WikiLinkReport()
        llm_config = self._config.require_llm()
        llm_config.require("wiki_link")
        now = self._clock()
        entries = catalog(load_wiki(self._wiki.files(), self._wiki.assets()))
        sig = signature(entries)
        links = self._wiki.read_links()
        notes = {note.meta.id: note for note in self._kb.all_notes()}
        todo = stale_notes(sorted(notes), links, sig)
        degradations: list[str] = []
        results = self._tag(
            [notes[n] for n in todo],
            entries,
            self._llm(week or iso_week(now), degradations),
            llm_config.chain("wiki_link")[0].batch_size,
            degradations,
        )
        merged = merge_links(
            links, results, entries=entries, sig=sig, existing=frozenset(notes), today=now.date()
        )
        self._wiki.write_links(merged)
        report = WikiLinkReport(
            processed=len(results),
            linked=sum(1 for n in merged.notes.values() if n.notions),
            candidates=len(merged.candidates),
            degradations=tuple(degradations),
        )
        logger.info("wiki link: %d notes tagged, %d to do", len(results), len(todo))
        return report

    def _llm(self, week: str, degradations: list[str]) -> StructuredLLM:
        usd, tokens = 0.0, 0
        for run in (self._triage.read(week), self._analyses.read(week)):
            if run is not None:
                more_usd, more_tokens = run.usage_totals()
                usd, tokens = usd + more_usd, tokens + more_tokens
        llm_config = self._config.require_llm()
        ledger = BudgetLedger(llm_config.weekly_budget, usd, tokens)

        def on_fallback(role: str, model_id: str, reason: str) -> None:
            degradations.append(f"fallback {role}: {model_id} ({reason})")

        return self._llm_factory(ledger, on_fallback)

    def _tag(
        self,
        notes: Sequence[Note],
        entries: Sequence[CatalogEntry],
        llm: StructuredLLM,
        size: int,
        degradations: list[str],
    ) -> dict[ItemId, LinkResult]:
        results: dict[ItemId, LinkResult] = {}
        for start in range(0, len(notes), size):
            chunk = notes[start : start + size]
            inputs = to_inputs(chunk)
            try:
                answer = llm.run(wiki_link_task(inputs, entries))
            except BudgetExhaustedError as exc:
                degradations.append(f"budget exhausted ({exc}): remaining notes not linked")
                break
            except ChainExhaustedError as exc:
                degradations.append(f"batch not linked: {exc}")
                continue
            by_ref = to_results(inputs, answer.output, entries)
            results.update(
                {
                    note.meta.id: by_ref[i.ref]
                    for note, i in zip(chunk, inputs, strict=True)
                    if i.ref in by_ref
                }
            )
        return results
