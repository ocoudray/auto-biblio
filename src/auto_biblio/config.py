"""Application settings, loaded from environment variables and an optional `.env` file."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from auto_biblio import __version__

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Typed, immutable application settings.

    Every field can be overridden with an environment variable prefixed with
    ``AUTO_BIBLIO_`` (e.g. ``AUTO_BIBLIO_LOG_LEVEL=DEBUG``).
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTO_BIBLIO_",
        env_file=".env",
        frozen=True,
    )

    log_level: LogLevel = "INFO"
    data_dir: Path = Path()
    github_token: SecretStr | None = None
    http_timeout_s: float = 30.0
    user_agent: str = f"auto-biblio/{__version__} (+https://github.com/ocoudray/auto-biblio)"
    data_repo: str | None = None
    """`owner/repo` of the data repository: feedback links and feedback issues."""
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    digest_to: str | None = None
    embeddings_cache_dir: Path = Path(".cache/embeddings")
