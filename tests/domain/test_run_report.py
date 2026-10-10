from datetime import UTC, datetime

from auto_biblio.domain.run_report import RunReport, SourceReport, SourceStatus

NOW = datetime(2026, 10, 10, 5, 0, tzinfo=UTC)


def make_report(*statuses: SourceStatus) -> RunReport:
    return RunReport(
        run_id="r",
        command="collect",
        started_at=NOW,
        finished_at=NOW,
        sources=tuple(SourceReport(source=f"s{i}", status=s) for i, s in enumerate(statuses)),
    )


def test_run_report_all_failed() -> None:
    assert make_report().all_failed is False
    assert make_report("failed", "failed").all_failed is True
    assert make_report("failed", "ok").all_failed is False
    assert make_report("skipped", "failed").all_failed is True
    assert make_report("skipped").all_failed is False


def test_run_report_any_ok() -> None:
    assert make_report("failed", "ok").any_ok is True
    assert make_report("skipped").any_ok is False
