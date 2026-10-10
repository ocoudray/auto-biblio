from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path

import httpx
import pytest
from builders import NOW, make_item
from typer.testing import CliRunner

from auto_biblio.cli import create_app, main
from auto_biblio.config import Settings
from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.domain.models import Clock, SourceBatch
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.sources import Source, SourceFactory

runner = CliRunner()


class FakeSource:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self._name = name
        self._fail = fail
        self.since: list[datetime] = []

    @property
    def name(self) -> str:
        return self._name

    def fetch(self, since: datetime) -> SourceBatch:
        self.since.append(since)
        if self._fail:
            raise SourceUnavailableError(self._name, "down")
        return SourceBatch(items=(make_item(source=self._name),))


def factory_of(*sources: FakeSource) -> SourceFactory:
    def build(
        _config: RepoConfig, _settings: Settings, _client: httpx.Client, _clock: Clock
    ) -> list[Source]:
        return list(sources)

    return build


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    result = runner.invoke(create_app(), ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    return tmp_path


def test_init_then_validate(data_dir: Path) -> None:
    result = runner.invoke(create_app(), ["validate-config", "--data-dir", str(data_dir)])
    assert result.exit_code == 0
    assert "valid" in result.output


def test_init_existing_exits_1(data_dir: Path) -> None:
    result = runner.invoke(create_app(), ["init", str(data_dir)])
    assert result.exit_code == 1
    assert "profile.yaml" in result.stderr


def test_validate_invalid_exits_1_with_field(data_dir: Path) -> None:
    sources = data_dir / "config" / "sources.yaml"
    sources.write_text("sources:\n  - {name: x, type: hackernews, min_points: lots}\n")
    result = runner.invoke(create_app(), ["validate-config", "--data-dir", str(data_dir)])
    assert result.exit_code == 1
    assert "config/sources.yaml: sources." in result.stderr


def test_collect_with_fake_factory(data_dir: Path) -> None:
    app = create_app(factory_of(FakeSource("a"), FakeSource("b")), clock=lambda: NOW)
    result = runner.invoke(app, ["collect", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert list((data_dir / "state" / "items").glob("*.jsonl"))
    assert (data_dir / "state" / "runs" / "20261010T050000Z-collect.json").exists()


def test_collect_invalid_config_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(create_app(factory_of()), ["collect", "--data-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "config/profile.yaml" in result.stderr


def test_collect_all_failed_exits_2(data_dir: Path) -> None:
    app = create_app(factory_of(FakeSource("a", fail=True)), clock=lambda: NOW)
    result = runner.invoke(app, ["collect", "--data-dir", str(data_dir)])
    assert result.exit_code == 2


def test_collect_only_and_since_forwarded(data_dir: Path) -> None:
    a, b = FakeSource("a"), FakeSource("b")
    app = create_app(factory_of(a, b), clock=lambda: NOW)
    args = ["collect", "--data-dir", str(data_dir), "--source", "b", "--since", "2026-09-01"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert a.since == []
    assert b.since == [datetime(2026, 9, 1, tzinfo=UTC)]


def test_collect_rejects_bad_since(data_dir: Path) -> None:
    app = create_app(factory_of(FakeSource("a")), clock=lambda: NOW)
    result = runner.invoke(app, ["collect", "--data-dir", str(data_dir), "--since", "yesterday"])
    assert result.exit_code != 0
    assert "since" in result.output.lower() + result.stderr.lower()


def test_entry_point_declared() -> None:
    names = {ep.name for ep in entry_points(group="console_scripts")}
    assert "auto-biblio" in names


def test_main_runs_real_app(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["auto-biblio", "validate-config", "--data-dir", str(data_dir)])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    assert "Configuration valid: 7 themes" in capsys.readouterr().out
