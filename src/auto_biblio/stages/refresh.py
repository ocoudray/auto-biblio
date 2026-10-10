"""Daily refresh of the popularity signals of known items."""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Clock, Item, Signal, SignalKind
from auto_biblio.domain.run_report import RunReport, SourceReport, SourceStatus
from auto_biblio.repo_config.triage import RefreshConfig
from auto_biblio.store.items import ItemStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.signals import SignalStore
from auto_biblio.store.triage import TriageStore

logger = logging.getLogger(__name__)

RECENT_RUNS = 4
"""Candidates of this many latest triage journals are refreshed first."""


class StarsReader(Protocol):
    """Reads GitHub stars (see `GithubStarsClient`)."""

    source: str

    def stars(self, repos: Sequence[str]) -> dict[str, int]:
        """Read the stars of repositories."""
        ...


class UpvotesReader(Protocol):
    """Reads Hugging Face upvotes (see `HfUpvotesClient`)."""

    source: str

    def upvotes(self, arxiv_id: str) -> int | None:
        """Read the upvotes of a paper."""
        ...


class SignalRefreshStage:
    """Re-reads stars and upvotes of recent items, within a daily cap."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        items: ItemStore,
        signals: SignalStore,
        triage: TriageStore,
        runs: RunStore,
        *,
        stars: StarsReader | None,
        upvotes: UpvotesReader,
        cfg: RefreshConfig,
        clock: Clock,
    ) -> None:
        """Build the stage.

        Args:
            items: Known items.
            signals: Where new observations go.
            triage: Past journals, to refresh recent candidates first.
            runs: Where the run report goes.
            stars: GitHub stars reader; None without GitHub token (stars are skipped).
            upvotes: Hugging Face upvotes reader.
            cfg: Horizon and daily cap.
            clock: Current time provider.
        """
        self._items = items
        self._signals = signals
        self._triage = triage
        self._runs = runs
        self._stars = stars
        self._upvotes = upvotes
        self._cfg = cfg
        self._clock = clock

    def run(self) -> RunReport:
        """Refresh the signals of the eligible items and write the run report.

        Returns:
            The report: one entry per reader.
        """
        started = self._clock()
        chosen = self._prioritized(started)[: self._cfg.max_items_per_day]
        repos = [i for i in chosen if _is_repo(i)]
        papers = [i for i in chosen if _is_hf_paper(i)]
        reports = (self._refresh_stars(repos, started), self._refresh_upvotes(papers, started))
        self._signals.flush()
        report = RunReport(
            run_id=f"{started:%Y%m%dT%H%M%SZ}-refresh",
            command="refresh",
            started_at=started,
            finished_at=self._clock(),
            sources=reports,
        )
        self._runs.write_report(report)
        return report

    def _prioritized(self, now: datetime) -> list[Item]:
        horizon = now - timedelta(days=self._cfg.horizon_days)
        recent_runs = self._triage.all()[-RECENT_RUNS:]
        candidates = {s.item_id for run in recent_runs for s in run.items}
        eligible = [
            i
            for i in self._items.all()
            if i.first_seen >= horizon and (_is_repo(i) or _is_hf_paper(i))
        ]
        return sorted(
            eligible, key=lambda i: (i.id not in candidates, -i.first_seen.timestamp(), i.id)
        )

    def _refresh_stars(self, repos: Sequence[Item], now: datetime) -> SourceReport:
        name = self._stars.source if self._stars else "refresh:gh_stars"
        if self._stars is None or not repos:
            return SourceReport(source=name, status="skipped")
        by_name = {i.id.removeprefix("gh:"): i.id for i in repos}
        try:
            stars = self._stars.stars(list(by_name))
        except (SourceUnavailableError, SourcePayloadError) as exc:
            logger.warning("star refresh failed: %s", exc)
            return SourceReport(source=name, status="failed", error=str(exc))
        found = {by_name[repo]: value for repo, value in stars.items() if repo in by_name}
        added = self._record(found, "gh_stars", now)
        return SourceReport(source=name, status="ok", received=len(found), signals=added)

    def _refresh_upvotes(self, papers: Sequence[Item], now: datetime) -> SourceReport:
        name = self._upvotes.source
        if not papers:
            return SourceReport(source=name, status="skipped")
        found: dict[ItemId, int] = {}
        errors: list[str] = []
        for paper in papers:
            try:
                value = self._upvotes.upvotes(paper.id.removeprefix("arxiv:"))
            except (SourceUnavailableError, SourcePayloadError) as exc:
                errors.append(str(exc))
                continue
            if value is not None:
                found[paper.id] = value
        added = self._record(found, "hf_upvotes", now)
        status: SourceStatus = "ok" if not errors else ("partial" if found else "failed")
        error = f"{len(errors)} failed, first: {errors[0]}" if errors else None
        return SourceReport(
            source=name, status=status, received=len(found), signals=added, error=error
        )

    def _record(self, values: dict[ItemId, int], kind: SignalKind, now: datetime) -> int:
        return self._signals.add(
            Signal(item_id=item_id, kind=kind, value=value, observed_at=now, source="refresh")
            for item_id, value in sorted(values.items())
        )


def _is_repo(item: Item) -> bool:
    return item.kind == "repo" and item.id.startswith("gh:") and "@" not in item.id


def _is_hf_paper(item: Item) -> bool:
    return item.id.startswith("arxiv:") and any(
        s.source_type == "hf_papers" for s in item.sightings
    )
