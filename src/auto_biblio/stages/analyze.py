"""Weekly analysis: notes for the selected items, one theme page, and the changelog."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from auto_biblio.domain.analysis import (
    AnalysisOutcome,
    AnalysisRun,
    NotePlan,
    OutcomeStatus,
    note_themes,
    pick_theme,
    plan_notes,
)
from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import (
    BudgetExhaustedError,
    ChainExhaustedError,
    KBFormatError,
    TriageRunMissingError,
)
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry, NoteChange, NoteChangeKind
from auto_biblio.domain.kb.notes import (
    Depth,
    Note,
    NoteMeta,
    ShortNote,
    merge_note,
    note_kind,
)
from auto_biblio.domain.kb.pages import RemovedLink, ThemePage, ThemePageMeta, page_links
from auto_biblio.domain.models import Clock, Item
from auto_biblio.domain.triage import LLMUsage, ScoredItem, TriageRun
from auto_biblio.extract import ExtractedText, TextExtractor
from auto_biblio.llm import StructuredLLM
from auto_biblio.llm.prompts import notes_v1, theme_page_v1
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.stages.triage import LLMFactory, iso_week
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.triage import TriageStore

logger = logging.getLogger(__name__)

VERSIONS: dict[Depth, str] = {"short": notes_v1.SHORT_VERSION, "deep": notes_v1.DEEP_VERSION}
_CHANGE: dict[OutcomeStatus, NoteChangeKind] = {
    "created": "created",
    "deepened": "deepened",
    "refreshed": "refreshed",
}


@dataclass
class _Week:
    """What the run accumulates."""

    now: datetime
    llm: StructuredLLM
    usage: list[LLMUsage] = field(default_factory=list[LLMUsage])
    degradations: list[str] = field(default_factory=list[str])
    budget_out: bool = False


@dataclass(frozen=True)
class _ThemeResult:
    theme: ThemeId | None
    links_added: tuple[str, ...] = ()
    links_removed: tuple[RemovedLink, ...] = ()


class AnalyzeStage:
    """Writes the knowledge base from the week's triage."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        config: RepoConfig,
        items: ItemStore,
        triage: TriageStore,
        analyses: AnalysisStore,
        kb: KBStore,
        *,
        extractor: TextExtractor,
        llm_factory: LLMFactory,
        clock: Clock,
    ) -> None:
        """Build the stage.

        Args:
            config: The data repository configuration.
            items: Collected items.
            triage: Weekly triage journals.
            analyses: Weekly analysis journals (read and written).
            kb: The knowledge base.
            extractor: Full-text extraction.
            llm_factory: Builds the LLM of the run from its budget ledger and fallback hook.
            clock: Current time provider.

        Raises:
            ConfigError: If `llm.yaml` is missing or lacks a chain for an analysis role.
        """
        self._config = config
        self._llm_config = config.require_llm()
        self._llm_config.require("short_note", "deep_analysis", "synthesis")
        self._cfg = config.analysis
        self._items = items
        self._triage = triage
        self._analyses = analyses
        self._kb = kb
        self._extractor = extractor
        self._llm_factory = llm_factory
        self._clock = clock

    def run(self, week: str | None = None) -> AnalysisRun:
        """Analyse the selection of a week and update the knowledge base.

        Args:
            week: ISO week (default: the current one). Re-running a week keeps what was done.

        Returns:
            The journal.

        Raises:
            TriageRunMissingError: If the week was not triaged.
        """
        now = self._clock()
        week = week or iso_week(now)
        triage_run = self._triage.read(week)
        if triage_run is None:
            raise TriageRunMissingError(week)
        previous = self._analyses.read(week)
        state = self._start(now, triage_run, previous)
        plans = plan_notes(
            triage_run,
            {n.meta.id: n.meta for n in self._kb.all_notes()},
            self._cfg.deep_count,
            VERSIONS,
        )
        outcomes = self._notes(plans, triage_run, state)
        merged = _merge_outcomes(outcomes, previous)
        theme = self._theme_page(merged, previous, state)
        changelog = self._changelog(week, merged, theme, previous, state)
        run = AnalysisRun(
            week=week,
            run_id=f"{now:%Y%m%dT%H%M%SZ}-analyze",
            generated_at=now,
            outcomes=merged,
            theme=theme.theme,
            changelog=changelog,
            usage=(*(previous.usage if previous else ()), *state.usage),
            degradations=tuple(state.degradations),
        )
        self._kb.write_changelog(changelog)
        self._analyses.write(run)
        return run

    def _start(self, now: datetime, triage_run: TriageRun, previous: AnalysisRun | None) -> _Week:
        usd, tokens = triage_run.usage_totals()
        if previous is not None:
            more_usd, more_tokens = previous.usage_totals()
            usd, tokens = usd + more_usd, tokens + more_tokens
        ledger = BudgetLedger(self._llm_config.weekly_budget, usd, tokens)
        degradations: list[str] = []

        def on_fallback(role: str, model_id: str, reason: str) -> None:
            degradations.append(f"fallback {role}: {model_id} ({reason})")

        return _Week(now=now, llm=self._llm_factory(ledger, on_fallback), degradations=degradations)

    def _notes(
        self, plans: Sequence[NotePlan], triage_run: TriageRun, state: _Week
    ) -> tuple[AnalysisOutcome, ...]:
        scored = {s.item_id: s for s in triage_run.items}
        # Short notes first: cheap, and they cover every item before the budget runs out.
        order = sorted(range(len(plans)), key=lambda i: plans[i].depth == "deep")
        outcomes: dict[int, AnalysisOutcome] = {}
        for index in order:
            outcomes[index] = self._note(plans[index], scored[plans[index].item_id], state)
        return tuple(outcomes[i] for i in range(len(plans)))

    def _note(self, plan: NotePlan, scored: ScoredItem, state: _Week) -> AnalysisOutcome:
        if plan.action == "skip":
            return _outcome(plan, "skipped")
        if state.budget_out:
            return _outcome(plan, "skipped", error="weekly budget exhausted")
        item = self._items.get(plan.item_id)
        if item is None:  # pragma: no cover - the triage journal comes from the same store
            return _outcome(plan, "failed", error="unknown item")
        try:
            note = self._write_note(plan, item, scored, state)
        except BudgetExhaustedError as exc:
            state.budget_out = True
            state.degradations.append(f"budget exhausted ({exc}): remaining notes skipped")
            return _outcome(plan, "skipped", error=str(exc))
        except (ChainExhaustedError, KBFormatError) as exc:
            state.degradations.append(f"note {plan.note_id} not written: {exc}")
            return _outcome(plan, "failed", error=str(exc))
        status: OutcomeStatus = "refreshed"
        if plan.action == "create":
            status = "created"
        elif plan.action == "deepen" and note.meta.depth == "deep":
            status = "deepened"
        return _outcome(plan, status, note=note)

    def _write_note(self, plan: NotePlan, item: Item, scored: ScoredItem, state: _Week) -> Note:
        extracted = self._text(plan, item, state)
        themes = self._config.profile.themes
        deep = plan.depth == "deep" and extracted.source == "full_text"
        content: ShortNote
        if deep:
            deep_result = state.llm.run(notes_v1.deep_analysis_task(item, extracted, themes))
            content, usage = deep_result.output, deep_result.usage
        else:
            short_result = state.llm.run(notes_v1.short_note_task(item, extracted, themes))
            content, usage = short_result.output, short_result.usage
        state.usage.append(usage)
        meta = self._meta(
            plan,
            item,
            scored=scored,
            extracted=extracted,
            model_id=usage.model_id,
            now=state.now,
            deep=deep,
        )
        note = merge_note(self._kb.get(plan.note_id), Note(meta=meta, content=content))
        self._kb.write_note(note)
        return note

    def _text(self, plan: NotePlan, item: Item, state: _Week) -> ExtractedText:
        if plan.depth == "short":
            if item.summary:
                return ExtractedText(text=item.summary, source="abstract")
            return ExtractedText(text=item.title, source="title")
        extracted = self._extractor.extract(item, self._cfg.max_input_chars)
        if extracted.source != "full_text":
            reason = "; ".join(extracted.errors) or "no full text for this kind of item"
            state.degradations.append(f"full text unavailable for {item.id}: {reason}")
        return extracted

    def _meta(  # noqa: PLR0913 - assembles the metadata from already computed parts
        self,
        plan: NotePlan,
        item: Item,
        *,
        scored: ScoredItem,
        extracted: ExtractedText,
        model_id: str,
        now: datetime,
        deep: bool,
    ) -> NoteMeta:
        release = plan.note_id != item.id
        repo = plan.note_id.removeprefix("gh:")
        code = [
            f"https://github.com/{i.removeprefix('gh:')}" for i in item.links if i.startswith("gh:")
        ]
        return NoteMeta(
            id=plan.note_id,
            kind=note_kind(item.kind),
            title=repo if release else item.title,
            url=f"https://github.com/{repo}" if release else str(item.url),
            themes=note_themes(scored, self._cfg.relevance_threshold),
            links=(*code, *((str(item.url),) if release else ())),
            related=tuple(ItemId(i) for i in item.links),
            depth="deep" if deep else "short",
            source_text=extracted.source,
            first_seen=item.first_seen.date(),
            analyzed_at=now.date(),
            model_id=model_id,
            prompt_version=VERSIONS["deep" if deep else "short"],
        )

    def _theme_page(
        self,
        outcomes: Sequence[AnalysisOutcome],
        previous: AnalysisRun | None,
        state: _Week,
    ) -> _ThemeResult:
        if previous is not None and previous.theme is not None:
            # The page of this week is already written: rewriting it would change it again.
            changelog = previous.changelog
            return _ThemeResult(previous.theme, changelog.links_added, changelog.links_removed)
        if state.budget_out:
            state.degradations.append("theme page skipped: weekly budget exhausted")
            return _ThemeResult(None)
        theme = self._pick(outcomes)
        notes = self._kb.notes_for_theme(theme)
        if not notes:
            return _ThemeResult(None)
        return self._rewrite(theme, notes, state)

    def _pick(self, outcomes: Sequence[AnalysisOutcome]) -> ThemeId:
        order = [ThemeId(t.id) for t in self._config.profile.themes]
        updated = {t: page.meta.updated_at for t in order if (page := self._kb.read_theme(t))}
        touched: set[ThemeId] = set()
        for outcome in outcomes:
            note = self._kb.get(outcome.note_id)
            if outcome.status in {"created", "deepened"} and note is not None:
                touched.update(note.meta.themes)
        return pick_theme(order, updated, frozenset(touched))

    def _rewrite(self, theme: ThemeId, notes: Sequence[Note], state: _Week) -> _ThemeResult:
        profile_theme = next(t for t in self._config.profile.themes if t.id == theme)
        old = self._kb.read_theme(theme)
        task = theme_page_v1.theme_page_task(
            profile_theme, old.content if old else None, notes, self._cfg.synthesis_max_chars
        )
        try:
            result = state.llm.run(task)
        except (ChainExhaustedError, BudgetExhaustedError) as exc:
            state.degradations.append(f"theme page {theme} kept as is: {exc}")
            return _ThemeResult(None)
        state.usage.append(result.usage)
        meta = ThemePageMeta(
            theme=theme,
            label=profile_theme.label,
            updated_at=state.now.date(),
            prompt_version=theme_page_v1.VERSION,
            model_id=result.usage.model_id,
            notes=tuple(n.meta.id for n in notes),
        )
        self._kb.write_theme(ThemePage(meta=meta, content=result.output))
        before = page_links(old.content) if old else frozenset[str]()
        added = tuple(sorted(page_links(result.output) - before))
        return _ThemeResult(theme, added, result.output.removed_links)

    def _changelog(
        self,
        week: str,
        outcomes: Sequence[AnalysisOutcome],
        theme: _ThemeResult,
        previous: AnalysisRun | None,
        state: _Week,
    ) -> ChangelogEntry:
        changes: list[NoteChange] = []
        for outcome in outcomes:
            note = self._kb.get(outcome.note_id)
            if outcome.status in _CHANGE and note is not None:
                changes.append(
                    NoteChange(
                        note_id=note.meta.id,
                        title=note.meta.title,
                        kind=note.meta.kind,
                        change=_CHANGE[outcome.status],
                        depth=note.meta.depth,
                        source_text=note.meta.source_text,
                    )
                )
        degradations = (*(previous.changelog.degradations if previous else ()), *state.degradations)
        return ChangelogEntry(
            week=week,
            notes=tuple(changes),
            theme=theme.theme,
            links_added=theme.links_added,
            links_removed=theme.links_removed,
            degradations=tuple(dict.fromkeys(degradations)),
        )


def _merge_outcomes(
    outcomes: Sequence[AnalysisOutcome], previous: AnalysisRun | None
) -> tuple[AnalysisOutcome, ...]:
    """Keep what an earlier run of the same week did for items this run skipped."""
    if previous is None:
        return tuple(outcomes)
    merged: list[AnalysisOutcome] = []
    for outcome in outcomes:
        earlier = previous.outcome_for(outcome.item_id)
        keep = outcome.status == "skipped" and earlier is not None and earlier.status != "skipped"
        merged.append(earlier if keep and earlier is not None else outcome)
    return tuple(merged)


def _outcome(
    plan: NotePlan, status: OutcomeStatus, *, note: Note | None = None, error: str | None = None
) -> AnalysisOutcome:
    return AnalysisOutcome(
        item_id=plan.item_id,
        note_id=plan.note_id,
        status=status,
        depth=note.meta.depth if note else None,
        source_text=note.meta.source_text if note else None,
        error=error,
    )
