"""Command-line interface: thin commands that parse input, call the stages and report."""

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import httpx
import typer

from auto_biblio import __version__
from auto_biblio.config import Settings
from auto_biblio.domain.errors import (
    ConfigError,
    MailDeliveryError,
    SiteBuildError,
    TriageRunMissingError,
)
from auto_biblio.domain.learning import FixedScoring, build_examples, evaluate_variants
from auto_biblio.domain.models import Clock
from auto_biblio.embeddings.cache import CachedEmbedder
from auto_biblio.integrations.github_issues import GithubIssues
from auto_biblio.log import configure_logging
from auto_biblio.repo_config.loader import RepoConfig, load_repo_config
from auto_biblio.scaffold import ScaffoldExistsError, scaffold_data_repo
from auto_biblio.sources import SourceFactory, build_sources
from auto_biblio.sources._http import Throttle
from auto_biblio.sources.context import ContextFetcher
from auto_biblio.sources.refresh import GithubStarsClient, HfUpvotesClient
from auto_biblio.stages.analyze import AnalyzeStage
from auto_biblio.stages.collect import CollectStage
from auto_biblio.stages.digest import DigestStage
from auto_biblio.stages.feedback import FeedbackStage
from auto_biblio.stages.refresh import SignalRefreshStage
from auto_biblio.stages.site import SiteStage
from auto_biblio.stages.triage import TriageStage
from auto_biblio.store.analysis import AnalysisStore
from auto_biblio.store.cursors import CursorStore
from auto_biblio.store.feedback import FeedbackStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.kb import KBStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.signals import SignalStore
from auto_biblio.store.triage import TriageStore
from auto_biblio.wiring import REAL_SERVICES, Services, llm_factory, usable_llm_config

logger = logging.getLogger(__name__)

EXIT_CONFIG_ERROR = 1
EXIT_ALL_SOURCES_FAILED = 2
EXIT_HEALTH_ALERT = 3
EXIT_MAIL_FAILED = 4
EXIT_SITE_FAILED = 5
HF_INTERVAL_S = 0.5
FULLTEXT_CACHE = Path(".cache/fulltext")
WEEK_PATTERN = re.compile(r"^\d{4}-W\d{2}$")

DataDirOption = Annotated[
    Path | None,
    typer.Option("--data-dir", help="Data repository root (default: AUTO_BIBLIO_DATA_DIR or .)."),
]


def _parse_week(value: str | None) -> str | None:
    if value is not None and not WEEK_PATTERN.match(value):
        message = f"--week must look like 2026-W41, got {value!r}"
        raise typer.BadParameter(message)
    return value


WeekOption = Annotated[
    str | None,
    typer.Option(
        "--week", help="ISO week, e.g. 2026-W41 (default: current or latest).", callback=_parse_week
    ),
]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_since(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        message = f"--since must be an ISO 8601 date or datetime, got {value!r}"
        raise typer.BadParameter(message) from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _fail(message: str, code: int) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code)


def _load_config(data_dir: Path) -> RepoConfig:
    try:
        return load_repo_config(data_dir)
    except ConfigError as exc:
        message = f"Invalid configuration: {exc}"
        raise _fail(message, EXIT_CONFIG_ERROR) from exc


def _http_client(settings: Settings) -> httpx.Client:
    headers = {"User-Agent": settings.user_agent}
    return httpx.Client(timeout=settings.http_timeout_s, headers=headers, follow_redirects=True)


def create_app(  # noqa: C901, PLR0915 - one nested function per command keeps them thin
    source_factory: SourceFactory = build_sources,
    clock: Clock = _utc_now,
    services: Services = REAL_SERVICES,
    http_client: Callable[[Settings], httpx.Client] = _http_client,
) -> typer.Typer:
    """Build the CLI application.

    Args:
        source_factory: Builds the connectors of a collect run (faked in tests).
        clock: Current time provider.
        services: Embedder, LLM runner and mail sender (faked in tests).
        http_client: Builds the HTTP client of a command (mocked in tests).

    Returns:
        The Typer application.
    """
    app = typer.Typer(no_args_is_help=True, help="Automated AI literature watch.")
    signals_app = typer.Typer(no_args_is_help=True, help="Popularity signals.")
    feedback_app = typer.Typer(no_args_is_help=True, help="Feedback on digest items.")
    eval_app = typer.Typer(no_args_is_help=True, help="Evaluation of the triage.")
    app.add_typer(signals_app, name="signals")
    app.add_typer(feedback_app, name="feedback")
    site_app = typer.Typer(no_args_is_help=True, help="Knowledge-base site.")
    app.add_typer(eval_app, name="eval")
    app.add_typer(site_app, name="site")
    settings = Settings()

    @app.callback()
    def _configure() -> None:
        configure_logging(settings.log_level)

    @app.command()
    def init(
        target: Annotated[Path, typer.Argument(help="Directory of the new data repository.")],
    ) -> None:
        """Create the configuration, workflow and state skeleton of a data repository."""
        try:
            created = scaffold_data_repo(target, __version__)
        except ScaffoldExistsError as exc:
            raise _fail(str(exc), EXIT_CONFIG_ERROR) from exc
        for path in created:
            typer.echo(f"created {path}")

    @app.command("validate-config")
    def validate_config(data_dir: DataDirOption = None) -> None:
        """Load and validate every configuration file."""
        config = _load_config(data_dir or settings.data_dir)
        typer.echo(
            f"Configuration valid: {len(config.profile.themes)} themes, "
            f"{len(config.sources.sources)} sources."
        )

    @app.command()
    def collect(
        data_dir: DataDirOption = None,
        source: Annotated[
            list[str] | None, typer.Option("--source", help="Only run this source (repeatable).")
        ] = None,
        since: Annotated[
            str | None, typer.Option("--since", help="ISO 8601 lower bound, overrides cursors.")
        ] = None,
    ) -> None:
        """Poll every enabled source and store new items and signals."""
        root = data_dir or settings.data_dir
        lower_bound = _parse_since(since)
        config = _load_config(root)
        state = root / "state"
        with http_client(settings) as client:
            stage = CollectStage(
                source_factory(config, settings, client, clock),
                ItemStore.open(state),
                SignalStore.open(state),
                CursorStore.open(state),
                RunStore(state),
                clock=clock,
                overlaps={s.name: timedelta(days=s.overlap_days) for s in config.sources.sources},
            )
            report = stage.run(only=set(source) if source else None, since=lower_bound)
        for entry in report.sources:
            typer.echo(f"{entry.source}: {entry.status} ({entry.received} items, {entry.new} new)")
        if report.all_failed:
            message = "Every source failed."
            raise _fail(message, EXIT_ALL_SOURCES_FAILED)

    @signals_app.command("refresh")
    def signals_refresh(data_dir: DataDirOption = None) -> None:
        """Re-read the stars and upvotes of recent items."""
        root = data_dir or settings.data_dir
        config = _load_config(root)
        state = root / "state"
        with http_client(settings) as client:
            token = settings.github_token
            stage = SignalRefreshStage(
                ItemStore.open(state),
                SignalStore.open(state),
                TriageStore(state),
                RunStore(state),
                stars=GithubStarsClient(client, token) if token else None,
                upvotes=HfUpvotesClient(client, Throttle(HF_INTERVAL_S)),
                cfg=config.triage.refresh,
                clock=clock,
            )
            report = stage.run()
        for entry in report.sources:
            typer.echo(f"{entry.source}: {entry.status} ({entry.signals} signals)")

    @feedback_app.command("ingest")
    def feedback_ingest(data_dir: DataDirOption = None) -> None:
        """Record the feedback issues of the data repository and close them."""
        root = data_dir or settings.data_dir
        _load_config(root)
        if settings.data_repo is None or settings.github_token is None:
            message = "feedback ingest needs AUTO_BIBLIO_DATA_REPO and AUTO_BIBLIO_GITHUB_TOKEN"
            raise _fail(message, EXIT_CONFIG_ERROR)
        with http_client(settings) as client:
            issues = GithubIssues(client, settings.data_repo, settings.github_token)
            report = FeedbackStage(issues, FeedbackStore.open(root / "state")).run()
        typer.echo(
            f"{report.ingested} ingested, {report.already_known} already known, "
            f"{report.invalid} invalid, {report.close_errors} update errors"
        )

    @app.command()
    def triage(data_dir: DataDirOption = None, week: WeekOption = None) -> None:
        """Triage the items of a week with the LLM and write the journal."""
        root = data_dir or settings.data_dir
        config = _load_config(root)
        try:
            llm_config = usable_llm_config(config.require_llm(), settings)
        except ConfigError as exc:
            message = f"Invalid configuration: {exc}"
            raise _fail(message, EXIT_CONFIG_ERROR) from exc
        config = config.model_copy(update={"llm": llm_config})
        state = root / "state"
        embedder = CachedEmbedder(services.embedder(settings), root / settings.embeddings_cache_dir)
        runner = services.model_runner(settings)
        with http_client(settings) as client:
            stage = TriageStage(
                config,
                ItemStore.open(state),
                SignalStore.open(state),
                FeedbackStore.open(state),
                TriageStore(state),
                embedder=embedder,
                llm_factory=llm_factory(runner, llm_config, state),
                context=ContextFetcher(
                    client, config.triage.context_max_words, settings.github_token
                ),
                clock=clock,
            )
            run = stage.run(week)
        embedder.flush()
        typer.echo(f"{run.week}: {len(run.items)} candidates, {len(run.selected())} selected")
        for degradation in run.degradations:
            typer.echo(f"degraded: {degradation}")

    @app.command()
    def analyze(data_dir: DataDirOption = None, week: WeekOption = None) -> None:
        """Write the notes, the theme page and the changelog of a triaged week."""
        root = data_dir or settings.data_dir
        config = _load_config(root)
        try:
            llm_config = usable_llm_config(config.require_llm(), settings)
            config = config.model_copy(update={"llm": llm_config})
            state = root / "state"
            runner = services.model_runner(settings)
            with http_client(settings) as client:
                stage = AnalyzeStage(
                    config,
                    ItemStore.open(state),
                    TriageStore(state),
                    AnalysisStore(state),
                    KBStore.open(root / "kb"),
                    extractor=services.extractor(settings, client, root / FULLTEXT_CACHE),
                    llm_factory=llm_factory(runner, llm_config, state),
                    clock=clock,
                )
                run = stage.run(week)
        except (ConfigError, TriageRunMissingError) as exc:
            raise _fail(str(exc), EXIT_CONFIG_ERROR) from exc
        changed = sum(o.status in {"created", "deepened", "refreshed"} for o in run.outcomes)
        typer.echo(f"{run.week}: {changed} notes written, theme page: {run.theme or 'none'}")
        for degradation in run.degradations:
            typer.echo(f"degraded: {degradation}")

    @site_app.command("build")
    def site_build(
        data_dir: DataDirOption = None,
        out: Annotated[Path, typer.Option("--out", help="Directory of the built site.")] = Path(
            "site"
        ),
    ) -> None:
        """Build the knowledge-base site: themes, notes, changelog and archived digests."""
        root = data_dir or settings.data_dir
        config = _load_config(root)
        state = root / "state"
        stage = SiteStage(
            config,
            KBStore.open(root / "kb"),
            TriageStore(state),
            ItemStore.open(state),
            AnalysisStore(state),
            builder=services.site_builder(),
        )
        try:
            plan = stage.run(out)
        except SiteBuildError as exc:
            raise _fail(str(exc), EXIT_SITE_FAILED) from exc
        typer.echo(f"site built in {out}: {len(plan.pages)} pages")
        for warning in plan.warnings:
            typer.echo(f"warning: {warning}")

    @app.command()
    def digest(
        data_dir: DataDirOption = None,
        week: WeekOption = None,
        dry_run: Annotated[
            Path | None, typer.Option("--dry-run", help="Write the HTML here instead of mailing.")
        ] = None,
    ) -> None:
        """Mail the digest of a triaged week."""
        root = data_dir or settings.data_dir
        config = _load_config(root)
        sender = services.mail_sender(settings)
        if dry_run is None and (sender is None or settings.digest_to is None):
            message = "sending needs AUTO_BIBLIO_SMTP_USER, _SMTP_PASSWORD and _DIGEST_TO"
            raise _fail(message, EXIT_CONFIG_ERROR)
        state = root / "state"
        stage = DigestStage(
            TriageStore(state),
            ItemStore.open(state),
            RunStore(state),
            config.profile,
            sender=sender,
            repo=settings.data_repo,
            to=settings.digest_to,
            clock=clock,
            kb=KBStore.open(root / "kb"),
            analyses=AnalysisStore(state),
            site_url=config.site.site_url,
        )
        try:
            mail = stage.run(week, dry_run_path=dry_run)
        except TriageRunMissingError as exc:
            raise _fail(str(exc), EXIT_CONFIG_ERROR) from exc
        except MailDeliveryError as exc:
            raise _fail(str(exc), EXIT_MAIL_FAILED) from exc
        typer.echo(f"{mail.subject}: {'written to ' + str(dry_run) if dry_run else 'sent'}")

    @eval_app.command("scoring")
    def eval_scoring(data_dir: DataDirOption = None) -> None:
        """Compare fixed and learned scoring on the reliable feedback labels."""
        root = data_dir or settings.data_dir
        cfg = _load_config(root).triage
        state = root / "state"
        examples = build_examples(
            TriageStore(state).all(),
            FeedbackStore.open(state).all(),
            clock(),
            cfg.learning.weak_negative_grace_days,
        )
        reliable = sum(e.reliable for e in examples)
        typer.echo(f"{reliable} reliable labels, {len(examples) - reliable} weak negatives")
        fixed = FixedScoring(cfg.weights, cfg.llm_weight)
        for name, auc in evaluate_variants(examples, cfg.learning, fixed).items():
            typer.echo(f"{name}: {'n/a' if auc is None else f'AUC {auc:.3f}'}")

    @app.command()
    def health(data_dir: DataDirOption = None) -> None:
        """Fail when the weekly triage has not run for too long."""
        root = data_dir or settings.data_dir
        cfg = _load_config(root).triage
        state = root / "state"
        now = clock()
        latest = TriageStore(state).latest()
        reports = RunStore(state).recent_reports(datetime.min.replace(tzinfo=UTC))
        since = latest.generated_at if latest else (reports[0].started_at if reports else now)
        age = now - since
        if age > timedelta(days=cfg.alert_after_days):
            message = f"no triage for {age.days} days (alert after {cfg.alert_after_days})"
            raise _fail(message, EXIT_HEALTH_ALERT)
        typer.echo(f"ok: last triage {latest.week if latest else 'none yet'}")

    return app


def main() -> None:
    """Console entry point (`auto-biblio`)."""
    create_app()()
