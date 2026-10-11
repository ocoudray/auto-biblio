"""Weekly analysis: which notes to write, which theme page to rewrite, and the journal."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry
from auto_biblio.domain.kb.notes import Depth, NoteMeta, SourceText, note_id_for
from auto_biblio.domain.triage import LLMUsage, ScoredItem, TriageRun

NoteAction = Literal["create", "deepen", "refresh", "skip"]
OutcomeStatus = Literal["created", "deepened", "refreshed", "skipped", "failed"]


class NotePlan(BaseModel):
    """What to do for one selected item."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    note_id: ItemId
    depth: Depth
    action: NoteAction


def plan_notes(
    run: TriageRun,
    existing: Mapping[ItemId, NoteMeta],
    deep_count: int,
    versions: Mapping[Depth, str],
) -> tuple[NotePlan, ...]:
    """Decide, for each item of the digest, which note to write.

    The `deep_count` best items of the themes get a deep note; the others, discoveries
    included, a short one. Items sharing a note (releases of one repository) are handled once,
    by the best ranked. An existing note is only rewritten to deepen it, or when the prompt of
    its depth changed.

    Args:
        run: The week's triage journal.
        existing: Metadata of the notes already in the knowledge base.
        deep_count: How many items get a deep note.
        versions: Current prompt version per depth.

    Returns:
        One plan per selected item, best first.
    """
    plans: list[NotePlan] = []
    seen: set[ItemId] = set()
    deep_left = deep_count
    for scored in run.selected():
        note_id = note_id_for(scored.item_id)
        if note_id in seen:
            plans.append(_plan(scored, note_id, "short", "skip"))
            continue
        seen.add(note_id)
        wanted: Depth = "deep" if scored.slot == "theme" and deep_left > 0 else "short"
        deep_left -= wanted == "deep"
        plans.append(_decide(scored, note_id, wanted, existing.get(note_id), versions))
    return tuple(plans)


def _plan(scored: ScoredItem, note_id: ItemId, depth: Depth, action: NoteAction) -> NotePlan:
    return NotePlan(item_id=scored.item_id, note_id=note_id, depth=depth, action=action)


def _decide(
    scored: ScoredItem,
    note_id: ItemId,
    wanted: Depth,
    current: NoteMeta | None,
    versions: Mapping[Depth, str],
) -> NotePlan:
    if current is None:
        return _plan(scored, note_id, wanted, "create")
    if current.depth == "short" and wanted == "deep":
        return _plan(scored, note_id, "deep", "deepen")
    if current.prompt_version != versions[current.depth]:
        return _plan(scored, note_id, current.depth, "refresh")
    return _plan(scored, note_id, current.depth, "skip")


def note_themes(scored: ScoredItem, threshold: int) -> tuple[ThemeId, ...]:
    """Choose the themes a note is attached to.

    Args:
        scored: The triaged item.
        threshold: Minimum LLM relevance (0-5) for a theme.

    Returns:
        The themes the LLM rated at least `threshold`, else the digest theme, else none.
    """
    if scored.verdict is not None:
        themes = tuple(sorted(t for t, s in scored.verdict.scores().items() if s >= threshold))
        if themes:
            return themes
    return (scored.theme,) if scored.theme is not None else ()


def pick_theme(
    order: Sequence[ThemeId], updated: Mapping[ThemeId, date], touched: frozenset[ThemeId]
) -> ThemeId:
    """Choose the theme page rewritten this week.

    Args:
        order: Themes in profile order (breaks ties).
        updated: Last rewrite of each existing page.
        touched: Themes that received a created or deepened note this week.

    Returns:
        The least recently updated theme among the touched ones (a missing page counts as
        oldest), or among all themes when none was touched.
    """
    pool = [t for t in order if t in touched] or list(order)
    return min(pool, key=lambda t: (updated.get(t, date.min), order.index(t)))


class AnalysisOutcome(BaseModel):
    """What happened to one selected item."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    note_id: ItemId
    status: OutcomeStatus
    depth: Depth | None = None
    source_text: SourceText | None = None
    error: str | None = None


class AnalysisRun(BaseModel):
    """The journal of one weekly analysis."""

    model_config = ConfigDict(frozen=True)

    week: str
    run_id: str
    generated_at: AwareDatetime
    outcomes: tuple[AnalysisOutcome, ...]
    theme: ThemeId | None
    changelog: ChangelogEntry
    usage: tuple[LLMUsage, ...] = ()
    degradations: tuple[str, ...] = ()

    def usage_totals(self) -> tuple[float, int]:
        """Sum what the LLM calls of this run consumed.

        Returns:
            Dollars spent and tokens consumed.
        """
        usd = sum(u.cost_usd for u in self.usage)
        tokens = sum(u.input_tokens + u.output_tokens for u in self.usage)
        return usd, tokens

    def outcome_for(self, item_id: ItemId) -> AnalysisOutcome | None:
        """Find the outcome of an item.

        Args:
            item_id: The item.

        Returns:
            Its outcome, if the item was selected.
        """
        return next((o for o in self.outcomes if o.item_id == item_id), None)
