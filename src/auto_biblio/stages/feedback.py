"""Ingestion of the feedback issues into `state/feedback/`."""

import logging
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.errors import FeedbackParseError, SourceUnavailableError
from auto_biblio.domain.feedback import FeedbackEvent, parse_issue_title, parse_issue_week
from auto_biblio.integrations.github_issues import INVALID_LABEL, Issue
from auto_biblio.store.feedback import FeedbackStore

logger = logging.getLogger(__name__)

RECORDED = "Feedback recorded, thanks."
INVALID = (
    "Could not read this feedback: {error}\n\n"
    "The title must be `👍 <item id>` or `👎 <item id>`; use the links of the digest."
)


class IssueTracker(Protocol):
    """What the stage needs from the issue tracker (see `GithubIssues`)."""

    def open_feedback(self) -> tuple[Issue, ...]:
        """List the open feedback issues."""
        ...

    def comment(self, number: int, body: str) -> None:
        """Comment on an issue."""
        ...

    def add_label(self, number: int, label: str) -> None:
        """Add a label to an issue."""
        ...

    def close(self, number: int) -> None:
        """Close an issue."""
        ...


class FeedbackReport(BaseModel):
    """Outcome of one ingestion."""

    model_config = ConfigDict(frozen=True)

    ingested: int
    already_known: int
    invalid: int
    close_errors: int


class FeedbackStage:
    """Turns feedback issues into events, then closes them."""

    def __init__(self, issues: IssueTracker, store: FeedbackStore) -> None:
        """Build the stage.

        Args:
            issues: The issue tracker of the data repository.
            store: Where events are recorded.
        """
        self._issues = issues
        self._store = store

    def run(self) -> FeedbackReport:
        """Ingest every open feedback issue.

        Events are flushed before any issue is closed, so that a closed issue is always
        recorded; a failed close only leaves the issue open for the next run.

        Returns:
            The counts of the run.
        """
        valid: list[Issue] = []
        invalid: list[tuple[Issue, FeedbackParseError]] = []
        ingested = 0
        for issue in self._issues.open_feedback():
            if INVALID_LABEL in issue.label_names:
                continue
            try:
                event = _event(issue)
            except FeedbackParseError as exc:
                invalid.append((issue, exc))
                continue
            valid.append(issue)
            ingested += self._store.add(event)
        self._store.flush()
        errors = sum(not self._close(issue) for issue in valid)
        errors += sum(not self._flag(issue, exc) for issue, exc in invalid)
        return FeedbackReport(
            ingested=ingested,
            already_known=len(valid) - ingested,
            invalid=len(invalid),
            close_errors=errors,
        )

    def _close(self, issue: Issue) -> bool:
        try:
            self._issues.comment(issue.number, RECORDED)
            self._issues.close(issue.number)
        except SourceUnavailableError as exc:
            logger.warning("could not close feedback issue #%d: %s", issue.number, exc)
            return False
        return True

    def _flag(self, issue: Issue, error: FeedbackParseError) -> bool:
        try:
            self._issues.comment(issue.number, INVALID.format(error=error))
            self._issues.add_label(issue.number, INVALID_LABEL)
        except SourceUnavailableError as exc:
            logger.warning("could not flag feedback issue #%d: %s", issue.number, exc)
            return False
        return True


def _event(issue: Issue) -> FeedbackEvent:
    origin = f"issue#{issue.number}"
    parsed = parse_issue_title(issue.title, origin)
    return FeedbackEvent(
        item_id=parsed.item_id,
        polarity=parsed.polarity,
        channel="explicit",
        at=issue.created_at,
        digest_week=parse_issue_week(issue.body),
        origin=origin,
    )
