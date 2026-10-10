"""Application settings, loaded from environment variables and an optional `.env` file."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

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
