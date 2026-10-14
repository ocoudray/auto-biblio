from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from pathlib import Path

import httpx
import pytest
import typer
from builders import NOW, make_item
from fakes import FakeEmbedder, PipelineRunner
from typer.testing import CliRunner

from auto_biblio.cli import create_app, main
from auto_biblio.config import Settings
from auto_biblio.domain.errors import MailDeliveryError, SiteBuildError, SourceUnavailableError
from auto_biblio.domain.models import Clock, Item, SourceBatch
from auto_biblio.extract import ExtractedText
from auto_biblio.publish import Mail
from auto_biblio.repo_config.loader import RepoConfig
from auto_biblio.sources import Source, SourceFactory
from auto_biblio.store.items import ItemStore
from auto_biblio.store.triage import TriageStore
from auto_biblio.website.builder import SiteBuilder
from auto_biblio.wiring import Services

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


def test_collect_uses_configured_overlap(data_dir: Path) -> None:
    arxiv = FakeSource("arxiv")
    app = create_app(factory_of(arxiv), clock=lambda: NOW)
    runner.invoke(app, ["collect", "--data-dir", str(data_dir)])
    later = create_app(factory_of(arxiv), clock=lambda: NOW + timedelta(days=1))
    runner.invoke(later, ["collect", "--data-dir", str(data_dir)])
    assert arxiv.since[1] == NOW - timedelta(days=5)


LLM_YAML = """
models:
  m: {id: "test:m", input_usd_per_mtok: 0, output_usd_per_mtok: 0, batch_size: 10}
chains: {triage: [m], short_note: [m], deep_analysis: [m], synthesis: [m]}
weekly_budget: {usd: 0, tokens: 1000000}
"""


class Outbox:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[Mail] = []
        self.fail = fail

    def send(self, mail: Mail) -> None:
        if self.fail:
            message = "smtp down"
            raise MailDeliveryError(message)
        self.sent.append(mail)


class FullText:
    def extract(self, item: Item, max_chars: int) -> ExtractedText:
        return ExtractedText(text=f"Full text of {item.title}"[:max_chars], source="full_text")


def services(outbox: Outbox | None = None) -> Services:
    return Services(
        embedder=lambda _s: FakeEmbedder(),
        model_runner=lambda _s: PipelineRunner(),
        mail_sender=lambda _s: outbox,
        extractor=lambda _s, _c, _d: FullText(),
        site_builder=SiteBuilder,
    )


def offline(_settings: Settings) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def app_with(outbox: Outbox | None = None, clock: Clock = lambda: NOW) -> typer.Typer:
    return create_app(factory_of(), clock=clock, services=services(outbox), http_client=offline)


@pytest.fixture
def triage_dir(data_dir: Path) -> Path:
    (data_dir / "config" / "llm.yaml").write_text(LLM_YAML)
    items = ItemStore.open(data_dir / "state")
    for i, title in enumerate(["Agent harness", "Agent memory", "Retrieval at scale", "Galaxies"]):
        items.upsert(
            make_item(item_id=f"arxiv:2410.0000{i}", title=title, seen_at=NOW - timedelta(days=2))
        )
    items.flush()
    return data_dir


def test_refresh_command(data_dir: Path) -> None:
    result = runner.invoke(app_with(), ["signals", "refresh", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "refresh:hf_upvotes: skipped" in result.output


def test_feedback_requires_repo(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_BIBLIO_DATA_REPO", raising=False)
    result = runner.invoke(app_with(), ["feedback", "ingest", "--data-dir", str(data_dir)])
    assert result.exit_code == 1
    assert "AUTO_BIBLIO_DATA_REPO" in result.stderr


def test_feedback_ingest(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_BIBLIO_DATA_REPO", "me/data")
    monkeypatch.setenv("AUTO_BIBLIO_GITHUB_TOKEN", "t")
    result = runner.invoke(app_with(), ["feedback", "ingest", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "0 ingested" in result.output


def test_triage_invalid_week(triage_dir: Path) -> None:
    result = runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir), "--week", "41"])
    assert result.exit_code != 0


def test_triage_needs_llm_config(data_dir: Path) -> None:
    result = runner.invoke(app_with(), ["triage", "--data-dir", str(data_dir)])
    assert result.exit_code == 1
    assert "llm.yaml" in result.stderr


def test_triage_then_digest_dry_run(triage_dir: Path, tmp_path: Path) -> None:
    result = runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    assert result.exit_code == 0, result.output
    assert "2026-W41" in result.output
    assert list((triage_dir / ".cache" / "embeddings").rglob("*.npz"))
    target = tmp_path / "digest.html"
    args = ["digest", "--data-dir", str(triage_dir), "--dry-run", str(target)]
    result = runner.invoke(app_with(), args)
    assert result.exit_code == 0, result.output
    latest = TriageStore(triage_dir / "state").latest()
    assert latest is not None
    shown = ItemStore.open(triage_dir / "state").get(latest.selected()[0].item_id)
    assert shown is not None
    assert shown.title in target.read_text()


def test_digest_sends(triage_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_BIBLIO_DIGEST_TO", "me@example.com")
    runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    outbox = Outbox()
    result = runner.invoke(app_with(outbox), ["digest", "--data-dir", str(triage_dir)])
    assert result.exit_code == 0, result.output
    assert len(outbox.sent) == 1


def test_digest_mail_failure(triage_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_BIBLIO_DIGEST_TO", "me@example.com")
    runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    result = runner.invoke(app_with(Outbox(fail=True)), ["digest", "--data-dir", str(triage_dir)])
    assert result.exit_code == 4


def test_digest_requires_smtp(triage_dir: Path) -> None:
    result = runner.invoke(app_with(None), ["digest", "--data-dir", str(triage_dir)])
    assert result.exit_code == 1
    assert "SMTP" in result.stderr


def test_digest_missing_week(triage_dir: Path, tmp_path: Path) -> None:
    args = [
        "digest",
        "--data-dir",
        str(triage_dir),
        "--week",
        "2026-W01",
        "--dry-run",
        str(tmp_path / "x.html"),
    ]
    result = runner.invoke(app_with(), args)
    assert result.exit_code == 1
    assert "2026-W01" in result.stderr


def test_eval_not_enough_labels(data_dir: Path) -> None:
    result = runner.invoke(app_with(), ["eval", "scoring", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "0 reliable labels" in result.output
    assert "fixed: n/a" in result.output


def test_health_ok_without_history(data_dir: Path) -> None:
    result = runner.invoke(app_with(), ["health", "--data-dir", str(data_dir)])
    assert result.exit_code == 0
    assert "none yet" in result.output


def test_health_alert(triage_dir: Path) -> None:
    runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    later = app_with(clock=lambda: NOW + timedelta(days=9))
    assert runner.invoke(later, ["health", "--data-dir", str(triage_dir)]).exit_code == 3
    assert runner.invoke(app_with(), ["health", "--data-dir", str(triage_dir)]).exit_code == 0


def test_analyze_command(triage_dir: Path, tmp_path: Path) -> None:
    runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    result = runner.invoke(app_with(), ["analyze", "--data-dir", str(triage_dir)])
    assert result.exit_code == 0, result.output
    assert "notes written" in result.output
    assert list((triage_dir / "kb" / "notes").rglob("*.md"))
    target = tmp_path / "digest.html"
    runner.invoke(app_with(), ["digest", "--data-dir", str(triage_dir), "--dry-run", str(target)])
    assert "Évolutions de la base" in target.read_text()


def test_analyze_needs_triage(triage_dir: Path) -> None:
    result = runner.invoke(app_with(), ["analyze", "--data-dir", str(triage_dir)])
    assert result.exit_code == 1
    assert "no triage journal" in result.stderr


def test_analyze_needs_roles(triage_dir: Path) -> None:
    llm = triage_dir / "config" / "llm.yaml"
    llm.write_text(
        llm.read_text().replace(", short_note: [m], deep_analysis: [m], synthesis: [m]", "")
    )
    runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    result = runner.invoke(app_with(), ["analyze", "--data-dir", str(triage_dir)])
    assert result.exit_code == 1
    assert "short_note" in result.stderr


def test_site_build_command(triage_dir: Path, tmp_path: Path) -> None:
    runner.invoke(app_with(), ["triage", "--data-dir", str(triage_dir)])
    runner.invoke(app_with(), ["analyze", "--data-dir", str(triage_dir)])
    out = tmp_path / "site"
    result = runner.invoke(
        app_with(), ["site", "build", "--data-dir", str(triage_dir), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert f"site built in {out}" in result.output
    assert (out / "index.html").exists()
    assert list((out / "digests").glob("*/index.html"))


class BrokenBuilder:
    def build(self, *_args: object) -> None:
        raise SiteBuildError("boom")


def test_site_build_failure(triage_dir: Path, tmp_path: Path) -> None:
    broken = replace(services(), site_builder=BrokenBuilder)
    app = create_app(factory_of(), clock=lambda: NOW, services=broken, http_client=offline)
    result = runner.invoke(
        app, ["site", "build", "--data-dir", str(triage_dir), "--out", str(tmp_path / "s")]
    )
    assert result.exit_code == 5
    assert "zensical build failed" in result.stderr
