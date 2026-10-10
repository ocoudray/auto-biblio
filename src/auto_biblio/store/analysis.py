"""Analysis journal store: one JSON file per ISO week."""

from pathlib import Path

from auto_biblio.domain.analysis import AnalysisRun
from auto_biblio.store._files import atomic_write_text


class AnalysisStore:
    """Weekly analysis journals in `state/analysis/YYYY-Www.json`."""

    def __init__(self, state_dir: Path) -> None:
        """Build the store.

        Args:
            state_dir: The data repository's `state/` directory.
        """
        self._dir = state_dir / "analysis"

    def read(self, week: str) -> AnalysisRun | None:
        """Read the journal of a week.

        Args:
            week: ISO week, `YYYY-Www`.

        Returns:
            The journal, if that week was analysed.
        """
        path = self._dir / f"{week}.json"
        if not path.exists():
            return None
        return AnalysisRun.model_validate_json(path.read_text(encoding="utf-8"))

    def write(self, run: AnalysisRun) -> Path:
        """Persist a journal, replacing the one of the same week.

        Args:
            run: The journal.

        Returns:
            The written file.
        """
        path = self._dir / f"{run.week}.json"
        atomic_write_text(path, run.model_dump_json(indent=2) + "\n")
        return path
