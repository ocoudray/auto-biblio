"""Read and validate the data repository configuration files."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from auto_biblio.domain.errors import ConfigError
from auto_biblio.repo_config.analysis import AnalysisConfig
from auto_biblio.repo_config.llm import LLMConfig
from auto_biblio.repo_config.profile import Profile
from auto_biblio.repo_config.site import SiteConfig
from auto_biblio.repo_config.sources import SourcesConfig
from auto_biblio.repo_config.triage import TriageConfig

PROFILE_PATH = Path("config/profile.yaml")
SOURCES_PATH = Path("config/sources.yaml")
LLM_PATH = Path("config/llm.yaml")
TRIAGE_PATH = Path("config/triage.yaml")
ANALYSIS_PATH = Path("config/analysis.yaml")
SITE_PATH = Path("config/site.yaml")


class RepoConfig(BaseModel):
    """The whole validated configuration of a data repository."""

    model_config = ConfigDict(frozen=True)

    profile: Profile
    sources: SourcesConfig
    triage: TriageConfig = TriageConfig()
    analysis: AnalysisConfig = AnalysisConfig()
    site: SiteConfig = SiteConfig()
    llm: LLMConfig | None = None
    """Absent until the repository is set up for triage; collection does not need it."""

    def require_llm(self) -> LLMConfig:
        """Return the LLM configuration of a repository set up for triage.

        Returns:
            The LLM configuration.

        Raises:
            ConfigError: If `config/llm.yaml` does not exist.
        """
        if self.llm is None:
            raise ConfigError(LLM_PATH.as_posix(), None, "file required for triage is missing")
        return self.llm


def load_repo_config(data_dir: Path) -> RepoConfig:
    """Load and validate every configuration file of a data repository.

    `triage.yaml`, `analysis.yaml` and `site.yaml` are optional (defaults apply), and so is
    `llm.yaml` (only the LLM steps need it).

    Args:
        data_dir: Root of the data repository.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: If a file is missing, is not valid YAML or does not match its schema.
    """
    triage_present = (data_dir / TRIAGE_PATH).exists()
    analysis_present = (data_dir / ANALYSIS_PATH).exists()
    llm_present = (data_dir / LLM_PATH).exists()
    site_present = (data_dir / SITE_PATH).exists()
    return RepoConfig(
        profile=_load(data_dir, PROFILE_PATH, Profile),
        sources=_load(data_dir, SOURCES_PATH, SourcesConfig),
        triage=_load(data_dir, TRIAGE_PATH, TriageConfig) if triage_present else TriageConfig(),
        analysis=(
            _load(data_dir, ANALYSIS_PATH, AnalysisConfig) if analysis_present else AnalysisConfig()
        ),
        site=_load(data_dir, SITE_PATH, SiteConfig) if site_present else SiteConfig(),
        llm=_load(data_dir, LLM_PATH, LLMConfig) if llm_present else None,
    )


def _load[ModelT: BaseModel](data_dir: Path, relative: Path, model: type[ModelT]) -> ModelT:
    shown = relative.as_posix()
    try:
        raw: object = yaml.safe_load((data_dir / relative).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(shown, None, f"cannot read file ({exc.strerror})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(shown, None, f"invalid YAML ({exc})") from exc
    if raw is None and model in {TriageConfig, AnalysisConfig, SiteConfig}:
        raw = {}  # an empty optional file means "all defaults"
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or None
        raise ConfigError(shown, field, first["msg"]) from exc
