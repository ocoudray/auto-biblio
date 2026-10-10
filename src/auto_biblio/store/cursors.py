"""Per-source cursors: when each source last succeeded."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from auto_biblio.store._files import atomic_write_text


class CursorStore:
    """Cursors persisted to `state/cursors.json` as sorted ISO 8601 UTC timestamps."""

    def __init__(self, path: Path, cursors: dict[str, datetime]) -> None:
        """Wrap already-loaded cursors; use `CursorStore.open` instead.

        Args:
            path: The `state/cursors.json` file.
            cursors: Loaded cursors by source name.
        """
        self._path = path
        self._cursors = cursors

    @classmethod
    def open(cls, state_dir: Path) -> Self:
        """Load the cursors stored under `state_dir` (none if the file does not exist).

        Args:
            state_dir: The data repository's `state/` directory.

        Returns:
            The store.
        """
        path = state_dir / "cursors.json"
        raw: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return cls(path, {name: datetime.fromisoformat(at) for name, at in raw.items()})

    def get(self, source: str) -> datetime | None:
        """Return when `source` last succeeded, if ever."""
        return self._cursors.get(source)

    def set(self, source: str, at: datetime) -> None:
        """Record that `source` succeeded at `at`."""
        self._cursors[source] = at

    def flush(self) -> None:
        """Write the cursors to disk."""
        payload = {
            name: at.astimezone(UTC).isoformat().replace("+00:00", "Z")
            for name, at in sorted(self._cursors.items())
        }
        atomic_write_text(self._path, json.dumps(payload, indent=2) + "\n")
