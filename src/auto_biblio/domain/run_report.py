"""Structured record of one pipeline run, per source."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

SourceStatus = Literal["ok", "partial", "failed", "skipped"]
"""`partial`: the source failed midway; what it returned is stored, its cursor is not moved."""


class SourceReport(BaseModel):
    """Outcome of one source during a run."""

    model_config = ConfigDict(frozen=True)

    source: str
    status: SourceStatus
    received: int = 0
    new: int = 0
    merged: int = 0
    signals: int = 0
    error: str | None = None


class RunReport(BaseModel):
    """Outcome of a whole run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    command: str
    started_at: AwareDatetime
    finished_at: AwareDatetime
    sources: tuple[SourceReport, ...]

    @property
    def any_ok(self) -> bool:
        """Whether at least one source brought results (fully or partially)."""
        return any(s.status in {"ok", "partial"} for s in self.sources)

    @property
    def all_failed(self) -> bool:
        """Whether at least one source failed and none brought results."""
        return not self.any_ok and any(s.status == "failed" for s in self.sources)
