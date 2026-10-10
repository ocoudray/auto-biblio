"""Run journal: one report per run, plus quarantined payloads."""

from pathlib import Path

from auto_biblio.domain.run_report import RunReport
from auto_biblio.store._files import atomic_write_text


class RunStore:
    """Writes to `state/runs/` and `state/quarantine/`."""

    def __init__(self, state_dir: Path) -> None:
        """Build the store.

        Args:
            state_dir: The data repository's `state/` directory.
        """
        self._state_dir = state_dir

    def write_report(self, report: RunReport) -> Path:
        """Persist a run report.

        Args:
            report: The finished run.

        Returns:
            The written file.
        """
        path = self._state_dir / "runs" / f"{report.run_id}.json"
        atomic_write_text(path, report.model_dump_json(indent=2) + "\n")
        return path

    def quarantine(self, run_id: str, source: str, excerpt: str) -> Path:
        """Keep a payload a source failed to parse, for later diagnosis.

        Args:
            run_id: The current run.
            source: The source that returned the payload.
            excerpt: The (truncated) raw payload.

        Returns:
            The written file.
        """
        path = self._state_dir / "quarantine" / run_id / f"{source}.txt"
        atomic_write_text(path, excerpt)
        return path
