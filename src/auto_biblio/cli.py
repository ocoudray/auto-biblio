"""Command-line interface: thin commands that parse input, call the stages and report."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from auto_biblio import __version__
from auto_biblio.config import Settings
from auto_biblio.domain.errors import ConfigError
from auto_biblio.domain.models import Clock
from auto_biblio.log import configure_logging
from auto_biblio.repo_config.loader import RepoConfig, load_repo_config
from auto_biblio.scaffold import ScaffoldExistsError, scaffold_data_repo
from auto_biblio.sources import SourceFactory, build_sources
from auto_biblio.stages.collect import CollectStage
from auto_biblio.store.cursors import CursorStore
from auto_biblio.store.items import ItemStore
from auto_biblio.store.runs import RunStore
from auto_biblio.store.signals import SignalStore

logger = logging.getLogger(__name__)

EXIT_CONFIG_ERROR = 1
EXIT_ALL_SOURCES_FAILED = 2

DataDirOption = Annotated[
    Path | None,
    typer.Option("--data-dir", help="Data repository root (default: AUTO_BIBLIO_DATA_DIR or .)."),
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


def create_app(
    source_factory: SourceFactory = build_sources, clock: Clock = _utc_now
) -> typer.Typer:
    """Build the CLI application.

    Args:
        source_factory: Builds the connectors of a collect run (faked in tests).
        clock: Current time provider.

    Returns:
        The Typer application.
    """
    app = typer.Typer(no_args_is_help=True, help="Automated AI literature watch.")
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
        headers = {"User-Agent": settings.user_agent}
        with httpx.Client(
            timeout=settings.http_timeout_s, headers=headers, follow_redirects=True
        ) as client:
            stage = CollectStage(
                source_factory(config, settings, client, clock),
                ItemStore.open(state),
                SignalStore.open(state),
                CursorStore.open(state),
                RunStore(state),
                clock=clock,
            )
            report = stage.run(only=set(source) if source else None, since=lower_bound)
        for entry in report.sources:
            typer.echo(f"{entry.source}: {entry.status} ({entry.received} items, {entry.new} new)")
        if report.all_failed:
            message = "Every source failed."
            raise _fail(message, EXIT_ALL_SOURCES_FAILED)

    return app


def main() -> None:
    """Console entry point (`auto-biblio`)."""
    create_app()()
