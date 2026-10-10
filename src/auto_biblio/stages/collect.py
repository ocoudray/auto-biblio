"""Collect stage: poll every source, merge what they return, record cursors and a report."""

import logging
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timedelta

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError
from auto_biblio.domain.models import Clock, SourceBatch
from auto_biblio.domain.run_report import RunReport, SourceReport
from auto_biblio.sources import Source
from auto_biblio.store.cursors import CursorStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.signals import SignalStore

logger = logging.getLogger(__name__)


class CollectStage:
    """Run every source once, isolating failures, and persist the results."""

    def __init__(  # noqa: PLR0913 - dependencies are injected explicitly
        self,
        sources: Sequence[Source],
        items: ItemStore,
        signals: SignalStore,
        cursors: CursorStore,
        runs: RunStore,
        *,
        clock: Clock,
        overlap: timedelta = timedelta(days=2),
        overlaps: Mapping[str, timedelta] | None = None,
        lookback: timedelta = timedelta(days=7),
    ) -> None:
        """Build the stage.

        Args:
            sources: Connectors to poll, in order.
            items: Item store.
            signals: Signal store.
            cursors: Per-source cursors.
            runs: Run journal.
            clock: Current time provider.
            overlap: How far before the cursor to look again (absorbs late publications).
            overlaps: Per-source overrides of `overlap`, by source name.
            lookback: How far back a source's first run looks.
        """
        self._sources = sources
        self._items = items
        self._signals = signals
        self._cursors = cursors
        self._runs = runs
        self._clock = clock
        self._overlap = overlap
        self._overlaps = dict(overlaps or {})
        self._lookback = lookback

    def run(
        self, *, only: Collection[str] | None = None, since: datetime | None = None
    ) -> RunReport:
        """Poll the sources and persist items, signals, cursors and the run report.

        Args:
            only: Names of the sources to run; the others are reported as skipped.
            since: Explicit lower bound overriding the cursors.

        Returns:
            The run report.
        """
        started = self._clock()
        run_id = f"{started:%Y%m%dT%H%M%SZ}-collect"
        reports = [
            self._run_source(source, run_id, since)
            if only is None or source.name in only
            else SourceReport(source=source.name, status="skipped")
            for source in self._sources
        ]
        self._items.flush()
        self._signals.flush()
        self._cursors.flush()
        report = RunReport(
            run_id=run_id,
            command="collect",
            started_at=started,
            finished_at=self._clock(),
            sources=tuple(reports),
        )
        self._runs.write_report(report)
        return report

    def _run_source(self, source: Source, run_id: str, since: datetime | None) -> SourceReport:
        fetched_at = self._clock()
        lower_bound = since or self._lower_bound(source.name, fetched_at)
        try:
            batch = source.fetch(lower_bound)
        except SourcePayloadError as exc:
            self._runs.quarantine(run_id, source.name, exc.payload_excerpt)
            return self._failed(source.name, exc)
        except SourceUnavailableError as exc:
            return self._failed(source.name, exc)
        except Exception as exc:
            # Last resort: a connector bug or an unforeseen payload must not abort the
            # whole run and lose the other sources' results. Logged with its traceback
            # and reported as a failed source, never swallowed.
            logger.exception("source %s crashed", source.name)
            return SourceReport(source=source.name, status="failed", error=repr(exc))
        report = self._store(source.name, batch)
        self._cursors.set(source.name, fetched_at)
        logger.info("%s: %d items (%d new), %d signals", *_summary(report))
        return report

    def _lower_bound(self, name: str, now: datetime) -> datetime:
        cursor = self._cursors.get(name)
        if cursor is None:
            return now - self._lookback
        return cursor - self._overlaps.get(name, self._overlap)

    def _store(self, name: str, batch: SourceBatch) -> SourceReport:
        outcomes = [self._items.upsert(item) for item in batch.items]
        return SourceReport(
            source=name,
            status="ok",
            received=len(batch.items),
            new=outcomes.count("new"),
            merged=outcomes.count("merged"),
            signals=self._signals.add(batch.signals),
        )

    @staticmethod
    def _failed(name: str, exc: Exception) -> SourceReport:
        logger.warning("source failed: %s", exc)
        return SourceReport(source=name, status="failed", error=str(exc))


def _summary(report: SourceReport) -> tuple[str, int, int, int]:
    return (report.source, report.received, report.new, report.signals)
