"""What the digest shows, independent of its rendering (pure)."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.feedback import feedback_issue_url
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry
from auto_biblio.domain.models import Item
from auto_biblio.domain.run_report import RunReport
from auto_biblio.domain.triage import ScoredItem, TriageRun
from auto_biblio.repo_config.profile import Profile


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class DigestItem(_Frozen):
    """One line of the digest."""

    title: str
    url: str
    sources: str
    reason: str | None
    item_type: str | None
    revenant: bool
    unverified: bool
    up_url: str | None
    down_url: str | None
    note_url: str | None = None
    verdict: str | None = None
    """One-sentence verdict of the deep analysis, when there is one."""


class ThemeSection(_Frozen):
    """The items of one theme."""

    label: str
    items: tuple[DigestItem, ...]


class SourceHealth(_Frozen):
    """A source failing on its latest runs."""

    source: str
    consecutive_failures: int


class HealthSummary(_Frozen):
    """Pipeline health shown in the digest footer."""

    failing_sources: tuple[SourceHealth, ...] = ()

    @classmethod
    def from_runs(cls, reports: Sequence[RunReport]) -> "HealthSummary":
        """Count, per source, how many of its latest runs failed in a row.

        Args:
            reports: Recent run reports, oldest first.

        Returns:
            The sources whose latest run failed.
        """
        history: defaultdict[str, list[bool]] = defaultdict(list)
        for report in reports:
            for source in report.sources:
                if source.status != "skipped":
                    history[source.source].append(source.status == "failed")
        failing: list[SourceHealth] = []
        for source, failures in sorted(history.items()):
            streak = 0
            for failed in reversed(failures):
                if not failed:
                    break
                streak += 1
            if streak:
                failing.append(SourceHealth(source=source, consecutive_failures=streak))
        return cls(failing_sources=tuple(failing))


class NoteLink(_Frozen):
    """Where the note of an item is, and its verdict when it is a deep one."""

    url: str
    verdict: str | None = None


class KBChange(_Frozen):
    """One line of the knowledge base changes."""

    title: str
    change: str
    url: str | None


class KBChanges(_Frozen):
    """What the knowledge base gained this week."""

    notes: tuple[KBChange, ...] = ()
    theme: str | None = None
    theme_url: str | None = None
    links_removed: tuple[str, ...] = ()
    """`<url> : <reason>` lines."""

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to show."""
        return not (self.notes or self.theme or self.links_removed)


_CHANGE_LABEL = {
    "created": "nouvelle fiche",
    "deepened": "fiche approfondie",
    "refreshed": "fiche réécrite",
}


def kb_url(repo: str | None, path: PurePosixPath) -> str | None:
    """Link to a file of the knowledge base on GitHub.

    Args:
        repo: `owner/repo` of the data repository.
        path: The file, relative to `kb/`.

    Returns:
        The URL, or None without repository.
    """
    return f"https://github.com/{repo}/blob/main/kb/{path}" if repo else None


def kb_changes(
    entry: ChangelogEntry,
    note_paths: Mapping[ItemId, PurePosixPath],
    profile: Profile,
    repo: str | None,
) -> KBChanges:
    """Turn the week's changelog into the digest section.

    Args:
        entry: The changelog of the week.
        note_paths: Location of each note.
        profile: The interest profile (theme labels).
        repo: `owner/repo` of the data repository.

    Returns:
        The section.
    """
    labels = {t.id: t.label for t in profile.themes}
    notes = tuple(
        KBChange(
            title=change.title,
            change=_CHANGE_LABEL[change.change],
            url=kb_url(repo, path) if (path := note_paths.get(change.note_id)) else None,
        )
        for change in entry.notes
    )
    theme_path = PurePosixPath("themes", f"{entry.theme}.md")
    return KBChanges(
        notes=notes,
        theme=labels.get(entry.theme, entry.theme) if entry.theme else None,
        theme_url=kb_url(repo, theme_path) if entry.theme else None,
        links_removed=tuple(f"{r.url} : {r.reason}" for r in entry.links_removed),
    )


class DigestView(_Frozen):
    """Everything the digest templates render."""

    week: str
    sections: tuple[ThemeSection, ...]
    discoveries: tuple[DigestItem, ...]
    health: HealthSummary
    scoring_version: str
    auc: float | None
    unverified: int
    cost_usd: float
    tokens: int
    degradations: tuple[str, ...]
    kb_changes: KBChanges = KBChanges()

    @property
    def count(self) -> int:
        """Number of items shown."""
        return sum(len(s.items) for s in self.sections) + len(self.discoveries)


def build_view(  # noqa: PLR0913 - the digest combines every weekly output
    run: TriageRun,
    items: Mapping[ItemId, Item],
    profile: Profile,
    health: HealthSummary,
    repo: str | None,
    *,
    notes: Mapping[ItemId, NoteLink] | None = None,
    changes: KBChanges | None = None,
) -> DigestView:
    """Assemble the digest of a triage run.

    Args:
        run: The weekly journal.
        items: The items of the run, by id.
        profile: The interest profile (theme labels and order).
        health: Pipeline health.
        repo: `owner/repo` of the data repository, for the feedback links (none without).
        notes: The note of each item that has one.
        changes: The knowledge base changes of the week.

    Returns:
        The view.
    """
    links = notes or {}
    by_theme: defaultdict[ThemeId | None, list[DigestItem]] = defaultdict(list)
    discoveries: list[DigestItem] = []
    for scored in run.selected():
        line = _line(scored, items[scored.item_id], run.week, repo, links.get(scored.item_id))
        if scored.slot == "discovery":
            discoveries.append(line)
        else:
            by_theme[scored.theme].append(line)
    sections = tuple(
        ThemeSection(label=t.label, items=tuple(by_theme[ThemeId(t.id)]))
        for t in profile.themes
        if by_theme[ThemeId(t.id)]
    )
    usd, tokens = run.usage_totals()
    auc = max(
        (a for a in (run.scoring.auc_without_weak, run.scoring.auc_with_weak) if a is not None),
        default=None,
    )
    return DigestView(
        week=run.week,
        sections=sections,
        discoveries=tuple(discoveries),
        health=health,
        scoring_version=run.scoring.version,
        auc=auc,
        unverified=sum(1 for s in run.selected() if s.verdict is None),
        cost_usd=usd,
        tokens=tokens,
        degradations=run.degradations,
        kb_changes=changes or KBChanges(),
    )


def _line(
    scored: ScoredItem, item: Item, week: str, repo: str | None, note: NoteLink | None
) -> DigestItem:
    verdict = scored.verdict
    sources = ", ".join(sorted({s.source for s in item.sightings}))
    return DigestItem(
        title=item.title,
        url=str(item.url),
        sources=sources,
        reason=verdict.reason if verdict else None,
        item_type=verdict.item_type if verdict else None,
        revenant=scored.features.revenant,
        unverified=verdict is None,
        up_url=feedback_issue_url(repo, item.id, 1, week) if repo else None,
        down_url=feedback_issue_url(repo, item.id, -1, week) if repo else None,
        note_url=note.url if note else None,
        verdict=note.verdict if note else None,
    )
