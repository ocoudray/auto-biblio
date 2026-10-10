"""What the digest shows, independent of its rendering (pure)."""

from collections import defaultdict
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.feedback import feedback_issue_url
from auto_biblio.domain.ids import ItemId
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

    @property
    def count(self) -> int:
        """Number of items shown."""
        return sum(len(s.items) for s in self.sections) + len(self.discoveries)


def build_view(
    run: TriageRun,
    items: Mapping[ItemId, Item],
    profile: Profile,
    health: HealthSummary,
    repo: str | None,
) -> DigestView:
    """Assemble the digest of a triage run.

    Args:
        run: The weekly journal.
        items: The items of the run, by id.
        profile: The interest profile (theme labels and order).
        health: Pipeline health.
        repo: `owner/repo` of the data repository, for the feedback links (none without).

    Returns:
        The view.
    """
    by_theme: defaultdict[ThemeId | None, list[DigestItem]] = defaultdict(list)
    discoveries: list[DigestItem] = []
    for scored in run.selected():
        line = _line(scored, items[scored.item_id], run.week, repo)
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
    )


def _line(scored: ScoredItem, item: Item, week: str, repo: str | None) -> DigestItem:
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
    )
