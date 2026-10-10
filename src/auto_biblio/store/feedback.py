"""Feedback store: one JSONL file per month of the reaction, unique per origin."""

from pathlib import Path
from typing import Self

from auto_biblio.domain.feedback import FeedbackEvent
from auto_biblio.store._files import atomic_write_text, month_key, read_lines


class FeedbackStore:
    """Feedback events persisted to `state/feedback/YYYY-MM.jsonl`."""

    def __init__(self, directory: Path, events: list[FeedbackEvent]) -> None:
        """Wrap already-loaded events; use `FeedbackStore.open` instead.

        Args:
            directory: The `state/feedback` directory.
            events: Loaded events.
        """
        self._dir = directory
        self._events = {event.origin: event for event in events}
        self._dirty: set[str] = set()

    @classmethod
    def open(cls, state_dir: Path) -> Self:
        """Load every event stored under `state_dir`.

        Args:
            state_dir: The data repository's `state/` directory.

        Returns:
            The store.
        """
        directory = state_dir / "feedback"
        events = [
            FeedbackEvent.model_validate_json(line)
            for path in sorted(directory.glob("*.jsonl"))
            for line in read_lines(path)
        ]
        return cls(directory, events)

    def add(self, event: FeedbackEvent) -> bool:
        """Record an event unless one with the same origin is already known.

        Args:
            event: The event.

        Returns:
            True if it was new.
        """
        if event.origin in self._events:
            return False
        self._events[event.origin] = event
        self._dirty.add(_partition(event))
        return True

    def all(self) -> tuple[FeedbackEvent, ...]:
        """Return every event, oldest first.

        Returns:
            The events.
        """
        return tuple(sorted(self._events.values(), key=lambda e: (e.at, e.origin)))

    def flush(self) -> None:
        """Rewrite the partitions changed since the last flush."""
        for key in sorted(self._dirty):
            events = [e for e in self.all() if _partition(e) == key]
            content = "".join(f"{e.model_dump_json()}\n" for e in events)
            atomic_write_text(self._dir / f"{key}.jsonl", content)
        self._dirty.clear()


def _partition(event: FeedbackEvent) -> str:
    return month_key(event.at.year, event.at.month)
