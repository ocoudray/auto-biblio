from datetime import timedelta
from pathlib import Path

from builders import NOW

from auto_biblio.domain.run_report import RunReport, SourceReport
from auto_biblio.store.runs import RunStore


def test_run_report_written(tmp_path: Path) -> None:
    report = RunReport(
        run_id="20261010T050000Z-collect",
        command="collect",
        started_at=NOW,
        finished_at=NOW,
        sources=(SourceReport(source="hn", status="ok", received=3),),
    )
    path = RunStore(tmp_path).write_report(report)
    assert path == tmp_path / "runs" / "20261010T050000Z-collect.json"
    assert RunReport.model_validate_json(path.read_text()) == report


def test_quarantine_written(tmp_path: Path) -> None:
    path = RunStore(tmp_path).quarantine("r1", "arxiv", "<broken")
    assert path == tmp_path / "quarantine" / "r1" / "arxiv.txt"
    assert path.read_text() == "<broken"


def test_recent_reports(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    for days in (10, 1, 3):
        started = NOW - timedelta(days=days)
        store.write_report(
            RunReport(
                run_id=f"r{days}",
                command="collect",
                started_at=started,
                finished_at=started,
                sources=(),
            )
        )
    recent = store.recent_reports(NOW - timedelta(days=5))
    assert [r.run_id for r in recent] == ["r3", "r1"]
    assert RunStore(tmp_path / "empty").recent_reports(NOW) == ()
