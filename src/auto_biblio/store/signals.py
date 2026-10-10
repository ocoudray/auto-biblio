"""Signal store: append-only observations, at most one per item, kind and day."""

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Self

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Signal, SignalKind
from auto_biblio.store._files import atomic_write_text, month_key, read_lines

type _Key = tuple[ItemId, SignalKind, date]


class SignalStore:
    """Signals persisted to `state/signals/YYYY-MM.jsonl` (month of `observed_at`)."""

    def __init__(self, directory: Path, by_month: dict[str, list[Signal]]) -> None:
        """Wrap already-loaded signals; use `SignalStore.open` instead.

        Args:
            directory: The `state/signals` directory.
            by_month: Loaded signals per partition.
        """
        self._dir = directory
        self._by_month = by_month
        self._keys: set[_Key] = {_key(s) for signals in by_month.values() for s in signals}
        self._dirty: set[str] = set()

    @classmethod
    def open(cls, state_dir: Path) -> Self:
        """Load every signal stored under `state_dir`.

        Args:
            state_dir: The data repository's `state/` directory.

        Returns:
            The store.
        """
        directory = state_dir / "signals"
        by_month = {
            path.stem: [Signal.model_validate_json(line) for line in read_lines(path)]
            for path in sorted(directory.glob("*.jsonl"))
        }
        return cls(directory, by_month)

    def add(self, signals: Iterable[Signal]) -> int:
        """Record signals, ignoring those already observed the same day.

        Args:
            signals: New observations.

        Returns:
            How many were actually recorded.
        """
        added = 0
        for signal in signals:
            key = _key(signal)
            if key in self._keys:
                continue
            self._keys.add(key)
            month = month_key(signal.observed_at.year, signal.observed_at.month)
            self._by_month.setdefault(month, []).append(signal)
            self._dirty.add(month)
            added += 1
        return added

    def flush(self) -> None:
        """Rewrite the partitions changed since the last flush."""
        for month in sorted(self._dirty):
            signals = sorted(
                self._by_month[month], key=lambda s: (s.observed_at, s.item_id, s.kind)
            )
            content = "".join(f"{s.model_dump_json()}\n" for s in signals)
            atomic_write_text(self._dir / f"{month}.jsonl", content)
        self._dirty.clear()


def _key(signal: Signal) -> _Key:
    return (signal.item_id, signal.kind, signal.observed_at.date())
