"""Read and validate the data repository configuration files."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from auto_biblio.domain.errors import ConfigError
from auto_biblio.repo_config.profile import Profile
from auto_biblio.repo_config.sources import SourcesConfig

PROFILE_PATH = Path("config/profile.yaml")
SOURCES_PATH = Path("config/sources.yaml")


class RepoConfig(BaseModel):
    """The whole validated configuration of a data repository."""

    model_config = ConfigDict(frozen=True)

    profile: Profile
    sources: SourcesConfig


def load_repo_config(data_dir: Path) -> RepoConfig:
    """Load and validate every configuration file of a data repository.

    Args:
        data_dir: Root of the data repository.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: If a file is missing, is not valid YAML or does not match its schema.
    """
    return RepoConfig(
        profile=_load(data_dir, PROFILE_PATH, Profile),
        sources=_load(data_dir, SOURCES_PATH, SourcesConfig),
    )


def _load[ModelT: BaseModel](data_dir: Path, relative: Path, model: type[ModelT]) -> ModelT:
    shown = relative.as_posix()
    try:
        raw: object = yaml.safe_load((data_dir / relative).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(shown, None, f"cannot read file ({exc.strerror})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(shown, None, f"invalid YAML ({exc})") from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or None
        raise ConfigError(shown, field, first["msg"]) from exc
