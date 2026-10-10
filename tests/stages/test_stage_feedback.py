from datetime import UTC, datetime
from pathlib import Path

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.integrations.github_issues import Issue
from auto_biblio.stages.feedback import FeedbackStage
from auto_biblio.store.feedback import FeedbackStore


def issue(number: int, title: str, labels: tuple[str, ...] = ()) -> Issue:
    return Issue.model_validate(
        {
            "number": number,
            "title": title,
            "body": "week: 2026-W41",
            "created_at": datetime(2026, 10, 9, tzinfo=UTC),
            "labels": [{"name": n} for n in ("feedback", *labels)],
        }
    )


def broken() -> SourceUnavailableError:
    return SourceUnavailableError("github-issues", "HTTP 502")


class Tracker:
    def __init__(
        self, issues: list[Issue], *, fail_close: bool = False, fail_label: bool = False
    ) -> None:
        self.issues = issues
        self.fail_close = fail_close
        self.fail_label = fail_label
        self.actions: list[tuple[str, int]] = []

    def open_feedback(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if ("close", i.number) not in self.actions)

    def comment(self, number: int, body: str) -> None:
        self.actions.append(("comment", number))
        self.last_body = body

    def add_label(self, number: int, label: str) -> None:
        if self.fail_label:
            raise broken()
        self.actions.append((f"label:{label}", number))

    def close(self, number: int) -> None:
        if self.fail_close:
            raise broken()
        self.actions.append(("close", number))


def test_ingest_creates_event_and_closes(tmp_path: Path) -> None:
    tracker = Tracker([issue(1, "👍 arxiv:2410.12345")])
    report = FeedbackStage(tracker, FeedbackStore.open(tmp_path)).run()
    assert report.ingested == 1
    assert tracker.actions == [("comment", 1), ("close", 1)]
    events = FeedbackStore.open(tmp_path).all()
    assert [(e.item_id, e.polarity, e.digest_week, e.origin) for e in events] == [
        ("arxiv:2410.12345", 1, "2026-W41", "issue#1")
    ]


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    tracker = Tracker([issue(1, "👎 gh:o/r")], fail_close=True)
    FeedbackStage(tracker, FeedbackStore.open(tmp_path)).run()
    tracker.fail_close = False
    report = FeedbackStage(tracker, FeedbackStore.open(tmp_path)).run()
    assert report.ingested == 0
    assert report.already_known == 1
    assert ("close", 1) in tracker.actions
    assert len(FeedbackStore.open(tmp_path).all()) == 1


def test_flush_before_close(tmp_path: Path) -> None:
    report = FeedbackStage(
        Tracker([issue(1, "👍 gh:o/r")], fail_close=True), FeedbackStore.open(tmp_path)
    ).run()
    assert report.close_errors == 1
    assert len(FeedbackStore.open(tmp_path).all()) == 1


def test_invalid_title_commented_and_labelled(tmp_path: Path) -> None:
    tracker = Tracker([issue(2, "great paper")])
    report = FeedbackStage(tracker, FeedbackStore.open(tmp_path)).run()
    assert report.invalid == 1
    assert tracker.actions == [("comment", 2), ("label:feedback-invalid", 2)]
    assert "great paper" in tracker.last_body
    assert FeedbackStore.open(tmp_path).all() == ()


def test_flag_failure_counted(tmp_path: Path) -> None:
    tracker = Tracker([issue(2, "bad")], fail_label=True)
    report = FeedbackStage(tracker, FeedbackStore.open(tmp_path)).run()
    assert report.close_errors == 1


def test_already_invalid_ignored(tmp_path: Path) -> None:
    tracker = Tracker([issue(3, "bad", labels=("feedback-invalid",))])
    report = FeedbackStage(tracker, FeedbackStore.open(tmp_path)).run()
    assert report.invalid == 0
    assert tracker.actions == []
