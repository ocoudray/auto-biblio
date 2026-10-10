"""Triage journal store: one JSON file per ISO week."""

from pathlib import Path

from auto_biblio.domain.triage import TriageRun
from auto_biblio.store._files import atomic_write_text


class TriageStore:
    """Weekly journals in `state/triage/YYYY-Www.json`."""

    def __init__(self, state_dir: Path) -> None:
        """Build the store.

        Args:
            state_dir: The data repository's `state/` directory.
        """
        self._dir = state_dir / "triage"

    def write(self, run: TriageRun) -> Path:
        """Persist a journal, replacing the one of the same week.

        Args:
            run: The journal.

        Returns:
            The written file.
        """
        path = self._dir / f"{run.week}.json"
        atomic_write_text(path, run.model_dump_json(indent=2) + "\n")
        return path

    def read(self, week: str) -> TriageRun | None:
        """Read the journal of a week.

        Args:
            week: ISO week, `YYYY-Www`.

        Returns:
            The journal, if that week was triaged.
        """
        path = self._dir / f"{week}.json"
        if not path.exists():
            return None
        return TriageRun.model_validate_json(path.read_text(encoding="utf-8"))

    def all(self) -> tuple[TriageRun, ...]:
        """Read every journal, oldest week first.

        Returns:
            The journals.
        """
        return tuple(
            TriageRun.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._dir.glob("*.json"))
        )

    def latest(self) -> TriageRun | None:
        """Read the most recent journal.

        Returns:
            The journal of the latest week, if any.
        """
        paths = sorted(self._dir.glob("*.json"))
        if not paths:
            return None
        return TriageRun.model_validate_json(paths[-1].read_text(encoding="utf-8"))
